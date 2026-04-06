#!/usr/bin/env python3
"""
Super Auto Editor — AI Documentary Video Editor
================================================
Analyzes the script with Gemini Pro, searches stock APIs for the best
matching media per scene, downloads and pre-processes clips, then renders
the final video with FFmpeg: avatar as the main track + B-roll overlays.

All media tracks are MUTED. Avatar audio is preserved throughout.
Output: 1920×1080 MP4.
"""

import json
import math
import os
import re
import time
import uuid
import hashlib
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import google.generativeai as genai

from config import Config


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _ffprobe_duration(path: str) -> float:
    """Return video/audio duration in seconds via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception:
        return 0.0


def _run_ffmpeg(args: List[str], label: str = "") -> bool:
    """Run FFmpeg command, return True on success."""
    cmd = ["ffmpeg", "-y"] + args
    try:
        subprocess.run(cmd, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode()[-800:] if e.stderr else ""
        print(f"   ✗ FFmpeg [{label}] failed: {err}")
        return False


def _safe_filename(name: str) -> str:
    return re.sub(r"[^\w\-.]", "_", name)[:60]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CLASS
# ─────────────────────────────────────────────────────────────────────────────

class SuperAutoEditor:
    """
    Full pipeline:
      PHASE 1 — Script Analysis   (Gemini Pro)
      PHASE 2 — Media Search      (Pexels / Pixabay / Unsplash / Brave / Serper)
      PHASE 3 — Pre-processing    (FFmpeg: scale, trim, mute)
      PHASE 4 — Rendering         (FFmpeg: avatar base + B-roll overlays)
    """

    # Fraction of video that may be covered by B-roll (prevents over-saturation)
    MAX_BROLL_COVERAGE = 0.75  # allow up to 75% so correction pass can reach 60%

    # ── Global coverage targets ────────────────────────────────────────────────
    MIN_COVERAGE     = 0.60   # MUST reach at least 60% coverage
    MAX_COVERAGE     = 0.70   # cap at 70%
    IMAGE_EXACT_DUR  = 3.0    # images are ALWAYS exactly 3 s
    IMAGE_MAX_DUR    = 3.0    # alias kept for compatibility
    VIDEO_MIN_DUR    = 5.0    # videos at least 5 s
    VIDEO_MAX_DUR    = 10.0   # videos at most 10 s
    MIN_GAP          = 3.0    # minimum silence between inserts
    MAX_GAP          = 20.0   # max allowed gap — media must appear every 20s
    SEARCH_TIMEOUT   = 3.0    # per-provider timeout in parallel search
    GOOD_SCORE_THRESH = 55.0  # early stop if we have 3+ candidates above this

    def __init__(
        self,
        gemini_keys:        list = None,
        pexels_key:         str  = "",
        pixabay_key:        str  = "",
        unsplash_key:       str  = "",
        brave_search_key:   str  = "",
        serper_key:         str  = "",
        google_search_key:  str  = "",   # format "API_KEY::CX_ID"
        videvo_key:         str  = "",
        coverr_key:         str  = "",
        progress_cb               = None,
    ):
        self.output_dir = Path(Config.OUTPUT_DIR)
        self.temp_dir   = Path(Config.TEMP_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        gem = ""
        if gemini_keys:
            for k in (gemini_keys if isinstance(gemini_keys, list) else [gemini_keys]):
                if k and k.strip():
                    gem = k.strip()
                    break

        # Google Custom Search: key and CX stored as "key::cx"
        gcs_key, gcs_cx = "", ""
        if google_search_key and "::" in google_search_key:
            parts = google_search_key.split("::", 1)
            gcs_key, gcs_cx = parts[0].strip(), parts[1].strip()
        elif google_search_key:
            gcs_key = google_search_key.strip()

        self.keys = {
            "gemini"      : gem,
            "pexels"      : pexels_key        or "",
            "pixabay"     : pixabay_key       or "",
            "unsplash"    : unsplash_key      or "",
            "brave_search": brave_search_key  or "",
            "serper"      : serper_key        or "",
            "gcs_key"     : gcs_key,
            "gcs_cx"      : gcs_cx,
            "videvo"      : videvo_key        or "",
            "coverr"      : coverr_key        or "",
        }
        self._progress_cb  = progress_cb
        self._url_cache: Dict[str, str] = {}   # url → local_path (session cache)

    # ─────────────────────────────────────────────────────────────────────────
    # PROGRESS REPORTER
    # ─────────────────────────────────────────────────────────────────────────

    def _progress(self, pct: int, msg: str):
        print(f"   [{pct:3d}%] {msg}")
        if callable(self._progress_cb):
            try:
                self._progress_cb(pct, msg)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, avatar_path: str, script: str, title: str = "super_auto_output") -> Dict:
        """
        Full pipeline. Returns dict with output_path, stats, scene_plan.
        On failure raises Exception.
        """
        job_dir = self.temp_dir / f"sae_{uuid.uuid4().hex[:8]}"
        job_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Detect avatar duration ────────────────────────────────────────
            self._progress(2, "Detecting avatar video duration…")
            duration = _ffprobe_duration(avatar_path)
            if duration <= 0:
                raise ValueError("Could not read avatar video duration.")
            self._progress(5, f"Avatar duration: {duration:.1f}s  ({duration/60:.1f} min)")

            # ── PHASE 1: Script Analysis ──────────────────────────────────────
            self._progress(8, "Analyzing script with Gemini AI…")
            scene_plan = self._analyze_script(script, duration)
            n_scenes = len(scene_plan.get("scenes", []))
            self._progress(25, f"Scene plan ready — {n_scenes} scenes identified")

            # ── PHASE 2: Media Search & Download ─────────────────────────────
            self._progress(28, "Searching stock media APIs…")
            scene_plan = self._search_and_download(scene_plan, job_dir)
            downloaded = sum(
                len([m for m in s.get("selected_media", []) if m.get("local_path")])
                for s in scene_plan["scenes"]
            )
            self._progress(60, f"Media ready — {downloaded} clips/images downloaded")

            # ── PHASE 3: Pre-process clips ────────────────────────────────────
            self._progress(62, "Pre-processing media clips (scale + mute)…")
            processed_timeline = self._preprocess_clips(scene_plan, job_dir, duration)
            self._progress(72, f"Pre-processing done — {len(processed_timeline)} media inserts")

            # ── PHASE 4: Render ───────────────────────────────────────────────
            ts       = int(time.time())
            safe_t   = _safe_filename(title) if title else "super_auto_output"
            out_name = f"{safe_t}_{ts}.mp4"
            out_path = str(self.output_dir / out_name)

            self._progress(74, "Rendering final video with FFmpeg…")
            self._render(avatar_path, processed_timeline, out_path)

            final_dur  = _ffprobe_duration(out_path)
            file_mb    = os.path.getsize(out_path) / 1_048_576
            self._progress(100, "Done!")

            result = {
                "output_path"    : out_path,
                "output_filename": out_name,
                "duration"       : final_dur,
                "duration_fmt"   : f"{int(final_dur//60)}:{int(final_dur%60):02d}",
                "file_size_mb"   : round(file_mb, 1),
                "scenes_count"   : n_scenes,
                "broll_count"    : len(processed_timeline),
                "scene_plan"     : scene_plan,
            }
            return result

        except Exception:
            raise

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 1 — GEMINI SCRIPT ANALYSIS
    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_script(self, script: str, duration_sec: float) -> Dict:
        """
        Send full script to Gemini Pro.
        Returns a structured scene plan with timing + search queries + decisions.
        """
        gem_key = self.keys.get("gemini", "")
        if not gem_key:
            raise ValueError("Gemini API key not configured. Add it in Settings → AI APIs.")

        genai.configure(api_key=gem_key)

        minutes = duration_sec / 60
        char_count = len(script)

        prompt = f"""You are an elite AI documentary video editor with 20 years of experience.
Your job: analyze this script and produce the most precise, visually-rich B-roll plan possible.

VIDEO DURATION: {duration_sec:.0f} seconds ({minutes:.1f} minutes)
SCRIPT LENGTH: {char_count:,} characters
TOTAL SCRIPT — READ EVERY WORD:
---
{script}
---

════════════ YOUR TASK ════════════
Create a PRODUCTION-READY scene plan. Think like the best YouTube documentary editor.
Every scene must have the RIGHT media for what is being SAID in that exact moment.

════════════ SCENE SPLITTING RULES ════════════
- Split ONLY by real topic shift, story beat change, or emotional pivot
- Each scene: 20–120 seconds depending on content
- For a {minutes:.1f}-minute video: aim for {max(8, int(minutes * 1.5))}-{max(15, int(minutes * 3))} scenes
- IMPORTANT: You must plan media so there is visual content at least every 20 seconds

════════════ MEDIA DECISION RULES (READ CAREFULLY) ════════════
Use "avatar_only" ONLY when the narrator is telling a deeply personal/emotional story
with zero visual reference. Maximum 20% of scenes can be avatar_only.

For EVERY OTHER scene, decide:
  "image"  → company logos, products, people (portraits), statistics, maps, documents
              Use image when: specific brand is mentioned, specific person is named,
              specific place is named, specific product is shown, data/numbers discussed
  "video"  → actions, processes, locations with motion, how-things-work demonstrations
              Use video when: an action verb is in the scene, a process is described,
              a place with activity is mentioned, something moving/happening
  "mixed"  → scene has multiple distinct visual moments (use 2 insertion_points)

CRITICAL: The media must match EXACTLY what is said. If the script says "Apple released
the iPhone", the media must show iPhone or Apple store — not generic tech footage.

════════════ ENTITY EXTRACTION (MOST IMPORTANT) ════════════
For each scene, identify:
- brand_entities: Real company/brand names mentioned (e.g. "Apple", "Tesla", "Nike")
- person_entities: Real people named (e.g. "Elon Musk", "Steve Jobs")
- place_entities: Real locations (e.g. "Paris", "Wall Street", "Silicon Valley")
- product_entities: Real products named (e.g. "iPhone 15", "Model S")

These entities need Brave web search for real, accurate images/footage.
brand_query: One precise search query using the entity name + context
  (e.g. "Apple iPhone 15 launch event", "Tesla Model S electric car driving")

════════════ SEARCH QUERIES RULES ════════════
- brand_query: ALWAYS use the real brand/entity name + specific context
  Examples: "Nike Air Max sneaker closeup", "SpaceX Falcon 9 launch footage"
- visual_queries: cinematic, documentary-style alternatives (for stock APIs)
  NEVER generic like "car", "people", "technology" — always specific to THIS scene
- 4-6 visual_queries per scene, from most specific to most general

════════════ TIMING RULES ════════════
- Total timing must equal exactly {duration_sec:.0f} seconds
- Start times sequential, no overlap
- Distribute proportionally: longer scenes for denser script sections

════════════ MEDIA PLACEMENT RULES ════════════
- "start": media at the beginning of the scene
- "middle": media in the strongest visual phrase
- "end": media just before topic shift
- Only one or two media inserts per scene maximum

Return ONLY valid JSON (no markdown, no explanation):

Return ONLY valid JSON (no markdown, no explanation):

{{
  "scenes": [
    {{
      "scene_id": 1,
      "title": "precise scene title",
      "summary": "one sentence — what is SAID in this scene specifically",
      "script_excerpt": "first 150 chars of this scene's script verbatim",
      "start_time": 0,
      "end_time": 45,
      "duration_seconds": 45,
      "tone": "informative|emotional|dramatic|energetic|neutral",
      "importance": "high|medium|low",
      "visual_richness": "rich|moderate|sparse",
      "decision": "avatar_only|image|video|mixed",
      "brand_entities": ["Apple", "Tesla"],
      "person_entities": ["Elon Musk"],
      "place_entities": ["Silicon Valley"],
      "product_entities": ["iPhone 15"],
      "brand_query": "Apple iPhone 15 launch event product photo",
      "search_queries": ["specific visual query 1", "cinematic query 2", "documentary query 3", "stock query 4"],
      "media_type_preferred": "video|image|none",
      "insertion_points": [
        {{
          "placement": "start|middle|end",
          "offset_from_scene_start": 5,
          "duration": 7,
          "reason": "why this exact media at this exact moment"
        }}
      ],
      "editor_notes": "what visual exactly should appear here"
    }}
  ],
  "total_duration": {duration_sec:.0f},
  "pacing_notes": "overall pacing assessment"
}}"""

        model = genai.GenerativeModel(
            Config.GEMINI_SCRIPT_MODEL,
            system_instruction=(
                "You are an expert AI documentary video editor with 20 years experience. "
                "Always return valid JSON only. Be extremely precise about entities and queries. "
                "NEVER use generic queries. Every query must match the exact script content."
            ),
        )
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.15, "max_output_tokens": 32768},
        )
        raw = response.text.strip()

        # Strip markdown code fences if model added them
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()

        try:
            plan = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                plan = json.loads(m.group())
            else:
                raise ValueError("Gemini returned invalid JSON for scene plan.")

        # Attach selected_media list and default missing fields to each scene
        for scene in plan.get("scenes", []):
            scene.setdefault("selected_media", [])
            scene.setdefault("brand_entities", [])
            scene.setdefault("person_entities", [])
            scene.setdefault("place_entities", [])
            scene.setdefault("product_entities", [])
            scene.setdefault("brand_query", "")

        return plan

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2 — SMART MEDIA SEARCH & DOWNLOAD
    #
    # Strategy (per scene, per insertion point):
    #   1. Run EVERY query through EVERY available API (no early break)
    #   2. Search priority: Brave Images → Serper Images → Pexels → Pixabay → Unsplash
    #      • Brave/Serper: broad web-level coverage, often the most specific hits
    #      • Pexels/Pixabay: reliable direct-download stock (video + photo)
    #      • Unsplash: high-quality photos as last resort for images
    #   3. Apply query-rank bonus: query[0] (most specific) gets +25, query[1] +18,
    #      query[2] +10, query[3] +5 — so relevant hits float to the top
    #   4. Video preference bonus when scene wants video
    #   5. Try up to 8 top candidates for download until one succeeds
    #   6. Never reuse a URL that was already placed in the video
    # ─────────────────────────────────────────────────────────────────────────

    # Query-rank score bonuses (most specific query should win)
    _QUERY_BONUS = [25, 18, 10, 5, 2, 0]

    def _search_and_download(self, plan: Dict, job_dir: Path) -> Dict:
        """
        Brain-driven search: score every scene, plan global density,
        search APIs in parallel waves, rank, download best candidates.
        """
        media_dir = job_dir / "media"
        media_dir.mkdir(exist_ok=True)
        used_urls: set = set()

        scenes   = plan.get("scenes", [])
        n        = len(scenes)
        duration = float(plan.get("total_duration", 0)) or sum(
            float(s.get("duration_seconds", 30)) for s in scenes
        )

        density  = self._plan_density(duration, n)
        apis_lbl = self._available_api_labels()
        self._progress(28, f"Media plan: target {density['target_inserts']} inserts "
                           f"| APIs: [{apis_lbl}]")

        inserts_placed = 0
        broll_seconds  = 0.0
        last_media_end = 0.0
        consecutive    = 0

        for idx, scene in enumerate(scenes):
            pct = 28 + int((idx / max(n, 1)) * 30)

            # ── Score the scene ───────────────────────────────────────────────
            score = self._score_scene(scene)
            scene["_brain"] = score   # store for debug

            if score["decision"] == "avatar_only":
                scene["selected_media"] = []
                consecutive = 0
                continue

            scene_start = float(scene.get("start_time", 0))
            scene_end   = float(scene.get("end_time", scene_start + 30))

            # ── Global density guards ─────────────────────────────────────────
            if inserts_placed >= density["max_inserts"]:
                scene["selected_media"] = []
                continue
            if broll_seconds >= duration * self.MAX_COVERAGE:
                scene["selected_media"] = []
                continue
            # Enforce minimum gap
            if scene_start < last_media_end + density["min_gap"]:
                scene["selected_media"] = []
                continue
            # Avoid 3 media scenes in a row (give avatar time)
            if consecutive >= 3:
                scene["selected_media"] = []
                consecutive = 0
                continue

            # ── Build parallel query waves ────────────────────────────────────
            wanted_type   = score["media_type"]   # "video" or "image"
            query_waves   = self._build_query_waves(scene)
            n_inserts     = min(score["insert_count"],
                                density["max_inserts"] - inserts_placed,
                                2)

            self._progress(pct, f"Scene {idx+1}/{n} [{wanted_type}] "
                                f"parallel search: {scene.get('title','')[:35]}")

            # ── Parallel search (waves) ───────────────────────────────────────
            candidates = self._parallel_search(query_waves, wanted_type)

            # Fallback: if wanted video but got nothing, try image
            if not candidates and wanted_type == "video":
                candidates = self._parallel_search(query_waves, "image")
                wanted_type = "image"

            if not candidates:
                scene["selected_media"] = []
                continue

            # Filter already-used
            candidates = [c for c in candidates if c.get("url") not in used_urls]
            if not candidates:
                scene["selected_media"] = []
                continue

            # Sort by score (best first)
            candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

            # ── Download top candidates for each insert ───────────────────────
            inserts_info = scene.get("insertion_points", [])
            if not inserts_info:
                inserts_info = [{
                    "offset_from_scene_start": scene_end * 0.3 - scene_start * 0.3,
                    "duration": 7 if wanted_type == "video" else 3,
                    "placement": "middle",
                }]

            selected   = []
            pool       = list(candidates)   # shrinks as we place items

            for insert in inserts_info[:n_inserts]:
                if not pool:
                    break

                raw_dur = float(insert.get("duration", 7 if wanted_type == "video" else 3))
                if wanted_type == "image":
                    clip_dur = self.IMAGE_EXACT_DUR   # images: always exactly 3 s
                else:
                    clip_dur = max(min(raw_dur, self.VIDEO_MAX_DUR), self.VIDEO_MIN_DUR)

                offset  = float(insert.get("offset_from_scene_start", 0))
                start_t = scene_start + offset
                end_t   = min(start_t + clip_dur, scene_end, duration - 0.5)
                actual  = end_t - start_t

                if actual < 1.5:
                    continue
                if start_t < last_media_end + density["min_gap"]:
                    continue
                if broll_seconds + actual > duration * self.MAX_COVERAGE:
                    break

                # Try downloading top candidates
                downloaded = self._download_best(pool[:6], media_dir,
                                                  scene["scene_id"])
                if not downloaded:
                    continue

                downloaded["insertion_offset"] = offset
                downloaded["clip_duration"]    = actual
                downloaded["placement"]        = insert.get("placement", "middle")
                selected.append(downloaded)
                used_urls.add(downloaded["url"])
                pool = [c for c in pool if c.get("url") != downloaded["url"]]

                broll_seconds  += actual
                last_media_end  = end_t
                inserts_placed += 1
                consecutive    += 1

            scene["selected_media"] = selected

        coverage = broll_seconds / max(duration, 1) * 100
        self._progress(55, f"Pass 1 done — {inserts_placed} inserts, {coverage:.0f}% coverage")

        # ── Second correction pass ────────────────────────────────────────────
        self._progress(56, "Running correction pass (opening hook / gap fill / coverage)…")
        plan = self._correction_pass(plan, media_dir, used_urls, duration)

        final_cov = self._compute_coverage(plan) / max(duration, 1) * 100
        self._progress(58, f"Media brain done — coverage {final_cov:.0f}%  "
                           f"(target ≥{self.MIN_COVERAGE*100:.0f}%)")
        return plan

    def _available_api_labels(self) -> str:
        labels = []
        if self.keys["brave_search"]: labels.append("Brave")
        if self.keys["serper"]:       labels.append("Serper")
        if self.keys["pexels"]:       labels.append("Pexels")
        if self.keys["pixabay"]:      labels.append("Pixabay")
        if self.keys["unsplash"]:     labels.append("Unsplash")
        if self.keys["gcs_key"]:      labels.append("Google")
        if self.keys["coverr"]:       labels.append("Coverr")
        if self.keys["videvo"]:       labels.append("Videvo")
        return ", ".join(labels) if labels else "no APIs configured"

    # ─────────────────────────────────────────────────────────────────────────
    # MEDIA BRAIN — scene scoring, density planning, query waves
    # ─────────────────────────────────────────────────────────────────────────

    _MOTION_WORDS = {
        "action","drive","run","walk","build","grow","move","fly","crash","fight",
        "swim","race","work","create","manufacture","produce","travel","climb","fall",
        "rise","flow","explode","launch","rush","evolve","transform","spread","attack",
        "march","celebrate","dance","compete","parade","fire","burn","flood","charge",
        "protest","fight","battle","war","storm","wave","speed","jump","leap",
    }
    _STATIC_WORDS = {
        "show","display","compare","define","explain","chart","logo","brand","person",
        "portrait","face","map","graph","data","statistics","product","object",
        "building","monument","symbol","document","certificate","flag","icon",
        "screen","interface","photo","image","picture","diagram","infographic",
    }
    _EMOTIONAL_WORDS = {
        "love","fear","hope","joy","pain","success","failure","dream","struggle",
        "victory","loss","grief","pride","anger","passion","inspiration","motivation",
        "courage","sacrifice","betrayal","emotion","feeling","heart","soul",
    }
    _DOCUMENTARY_WORDS = {
        "history","historical","war","factory","city","nature","documentary","archive",
        "archival","vintage","classic","era","period","decade","century","event",
        "revolution","movement","discovery","invention","industrial","ancient",
    }
    _TRANSITION_WORDS = {
        "now","next","so","but","therefore","however","meanwhile","finally","also",
        "remember","consider","think","imagine","let","as","while","although",
    }

    def _score_scene(self, scene: Dict) -> Dict:
        """
        Score a scene on 6 dimensions and return decision + media_type.
        Returns dict: {visual_need, decision, media_type, insert_count}
        """
        text = (
            (scene.get("title", "") + " " +
             scene.get("summary", "") + " " +
             scene.get("script_excerpt", "")).lower()
        )
        words = set(re.findall(r"\b\w+\b", text))
        dur   = float(scene.get("duration_seconds", 30))

        # Dimension scores 0-100
        motion_hits      = len(words & self._MOTION_WORDS)
        static_hits      = len(words & self._STATIC_WORDS)
        emotional_hits   = len(words & self._EMOTIONAL_WORDS)
        documentary_hits = len(words & self._DOCUMENTARY_WORDS)
        transition_hits  = len(words & self._TRANSITION_WORDS)

        visual_need  = min(100, (motion_hits * 15) + (static_hits * 10) + (documentary_hits * 12))
        emotional    = min(100, emotional_hits * 20)
        explanatory  = min(100, static_hits * 15)
        importance_map = {"high": 80, "medium": 50, "low": 20}
        importance   = importance_map.get(scene.get("importance", "medium"), 50)
        richness_map = {"rich": 80, "moderate": 50, "sparse": 20}
        richness     = richness_map.get(scene.get("visual_richness", "moderate"), 50)

        # Is this mostly a transition sentence?
        is_transition = (transition_hits >= 3 and motion_hits == 0
                         and static_hits == 0 and dur < 20)

        media_priority = (
            visual_need  * 0.30 +
            emotional    * 0.15 +
            explanatory  * 0.15 +
            importance   * 0.25 +
            richness     * 0.15
        )

        # Decision logic — be generous with media, only skip if truly transition-only
        if is_transition and media_priority < 20:
            decision   = "avatar_only"
            media_type = "none"
        elif motion_hits > static_hits or documentary_hits >= 2 or media_priority >= 60:
            decision   = "video_support"
            media_type = "video"
        else:
            # Default to image — static content, facts, explanations, brands
            decision   = "image_support"
            media_type = "image"

        # How many inserts: 1 default, 2 for high-importance/long scenes
        insert_count = 2 if (importance >= 70 and dur >= 30) else 1

        return {
            "visual_need"    : visual_need,
            "media_priority" : media_priority,
            "decision"       : decision,
            "media_type"     : media_type,
            "insert_count"   : insert_count,
        }

    def _plan_density(self, duration: float, n_scenes: int) -> Dict:
        """
        Compute target insert count to reach ≥50 % coverage.
        Mix of 3 s images and 7 s videos → average ~5.5 s per insert.
        """
        minutes = duration / 60.0
        avg_insert_dur = 5.5   # realistic mix average
        target_inserts = int((duration * self.MIN_COVERAGE) / avg_insert_dur)
        max_inserts    = int((duration * self.MAX_COVERAGE) / avg_insert_dur)

        # Sanity caps — prevent absurdly dense timelines on long videos
        if minutes <= 1:
            target_inserts = min(target_inserts, 8)
            max_inserts    = min(max_inserts, 10)
        elif minutes <= 5:
            target_inserts = min(target_inserts, 28)
            max_inserts    = min(max_inserts, 36)
        elif minutes <= 10:
            target_inserts = min(target_inserts, 55)
            max_inserts    = min(max_inserts, 70)
        else:
            target_inserts = min(target_inserts, int(minutes * 4.5))
            max_inserts    = min(max_inserts,    int(minutes * 6.0))

        return {
            "target_inserts" : max(4, target_inserts),
            "max_inserts"    : max(4, max_inserts),
            "min_gap"        : self.MIN_GAP,
            "max_gap"        : self.MAX_GAP,
        }

    # Common words to ignore when extracting entities
    _ENTITY_STOPWORDS = {
        "the","a","an","and","or","but","in","on","at","to","for","of","with",
        "by","from","up","as","into","through","during","before","after","above",
        "below","between","each","few","more","most","other","some","such","no",
        "nor","not","only","own","same","so","than","too","very","just","this",
        "that","these","those","is","are","was","were","be","been","has","have",
        "had","do","does","did","will","would","could","should","may","might",
        "shall","can","their","they","them","he","she","we","you","i","it","its",
        "his","her","our","who","which","what","when","where","how","why","both",
        "video","story","time","year","day","world","people","company","brand",
        "product","market","industry","business","service","system","model",
    }

    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract proper nouns and brand names from text.
        Returns up to 4 unique entity strings (most likely to be searchable).
        """
        words   = re.findall(r"\b[A-Z][a-zA-Z]{1,30}\b", text)
        seen: set = set()
        entities: List[str] = []
        for w in words:
            lw = w.lower()
            if lw in self._ENTITY_STOPWORDS:
                continue
            if w not in seen:
                seen.add(w)
                entities.append(w)
        return entities[:4]

    def _build_query_waves(self, scene: Dict) -> List[List[str]]:
        """
        Return 3 waves of queries:
          Wave 0 — brand/entity-specific (Brave-first, highest bonus)
          Wave 1 — Gemini's exact visual queries (stock APIs)
          Wave 2 — cinematic/documentary broad fallback
        """
        base         = scene.get("search_queries", [])
        brand_query  = scene.get("brand_query", "")
        title        = scene.get("title", "")
        summ         = scene.get("summary", "")
        excerpt      = scene.get("script_excerpt", "")

        # Entities from Gemini plan (most accurate)
        brand_ents   = scene.get("brand_entities", [])
        person_ents  = scene.get("person_entities", [])
        place_ents   = scene.get("place_entities", [])
        product_ents = scene.get("product_entities", [])
        all_entities = brand_ents + person_ents + place_ents + product_ents

        # Fallback: extract from text if Gemini didn't provide
        if not all_entities:
            all_entities = self._extract_entities(
                title + " " + summ + " " + excerpt[:200]
            )

        topic = title or summ[:60]

        # ── Wave 0: entity/brand queries — Brave will be called FIRST on these ──
        # These are the most specific — real company names, people, products
        wave0: List[str] = []
        if brand_query:
            wave0.append(brand_query)             # Gemini's precise brand query
        for ent in all_entities[:3]:
            wave0.append(ent)                     # exact entity name
            wave0.append(f"{ent} photo")          # entity + context
        wave0 = list(dict.fromkeys(w for w in wave0 if w))[:5]

        # ── Wave 1: Gemini's visual queries for stock APIs ────────────────────
        wave1: List[str] = list(dict.fromkeys(base[:5])) if base else [topic]

        # ── Wave 2: cinematic/documentary fallback ────────────────────────────
        wave2: List[str] = []
        for q in (base[:2] if base else [topic]):
            wave2.append(f"cinematic {q}")
        words = [w for w in topic.split() if len(w) > 4][:4]
        broad = " ".join(words) if words else topic
        wave2.append(f"documentary footage {broad}")
        wave2.append(broad)
        wave2 = list(dict.fromkeys(wave2))[:4]

        return [wave0, wave1, wave2]

    # ─────────────────────────────────────────────────────────────────────────
    # CORRECTION PASS — opening hook, gap fill, coverage enforcement
    # ─────────────────────────────────────────────────────────────────────────

    def _build_timeline_from_plan(self, plan: Dict) -> List[Tuple[float, float]]:
        """Return sorted list of (abs_start, abs_end) for every downloaded media."""
        items = []
        for scene in plan.get("scenes", []):
            s = float(scene.get("start_time", 0))
            for media in scene.get("selected_media", []):
                if not media.get("local_path"):
                    continue
                offset = float(media.get("insertion_offset", 0))
                dur    = float(media.get("clip_duration", 3))
                a      = s + offset
                items.append((a, a + dur))
        items.sort()
        return items

    def _compute_coverage(self, plan: Dict) -> float:
        """Total seconds of media in the plan (sum of all clip_duration with local_path)."""
        total = 0.0
        for scene in plan.get("scenes", []):
            for media in scene.get("selected_media", []):
                if media.get("local_path"):
                    total += float(media.get("clip_duration", 3))
        return total

    def _inject_media(
        self,
        scene: Dict,
        media_dir: Path,
        used_urls: set,
        offset: float,
        clip_dur: float,
        label: str,
        prefer_type: str = "image",
    ) -> bool:
        """
        Search + download one media item and append it to scene['selected_media'].
        Returns True if successful.
        """
        waves = self._build_query_waves(scene)
        candidates = self._parallel_search(waves, prefer_type)
        if not candidates and prefer_type == "video":
            candidates = self._parallel_search(waves, "image")
            prefer_type = "image"
        if not candidates:
            return False

        candidates = [c for c in candidates if c.get("url") not in used_urls]
        if not candidates:
            return False

        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        dl = self._download_best(candidates[:6], media_dir, label)
        if not dl:
            return False

        actual_type = dl.get("type", prefer_type)
        dur = self.IMAGE_EXACT_DUR if actual_type == "image" else clip_dur
        dl["insertion_offset"] = offset
        dl["clip_duration"]    = dur
        dl["placement"]        = "corrected"
        scene.setdefault("selected_media", []).append(dl)
        used_urls.add(dl["url"])
        return True

    def _correction_pass(
        self,
        plan: Dict,
        media_dir: Path,
        used_urls: set,
        duration: float,
    ) -> Dict:
        """
        Second pass — enforces three rules:
          1. Opening hook: media MUST appear in the first 3 seconds
          2. No gap longer than MAX_GAP (16 s) without media
          3. Total coverage must reach MIN_COVERAGE (50 %)
        Mutates plan in-place; returns updated plan.
        """
        scenes = plan.get("scenes", [])
        if not scenes:
            return plan

        def _rebuild():
            return self._build_timeline_from_plan(plan)

        # ── 1. Opening hook (first 3 seconds must have media) ─────────────────
        tl = _rebuild()
        has_opening = tl and tl[0][0] <= 3.0
        if not has_opening:
            first = scenes[0]
            brain = first.get("_brain", {})
            if brain.get("decision") != "avatar_only":
                prefer = brain.get("media_type", "video")
                s_dur  = float(first.get("duration_seconds", 30))
                dur    = self.IMAGE_EXACT_DUR if prefer == "image" else min(7.0, s_dur * 0.35)
                ok = self._inject_media(first, media_dir, used_urls,
                                        offset=0.0, clip_dur=dur,
                                        label="opening", prefer_type=prefer)
                if ok:
                    self._progress(56, "Opening hook injected")
                    tl = _rebuild()

        # ── 2. Gap filling (gaps > MAX_GAP seconds) ───────────────────────────
        max_iters = 30   # safety limit on correction iterations
        iters = 0
        while iters < max_iters:
            tl = _rebuild()
            prev_end    = 0.0
            gap_fixed   = False
            for seg_start, seg_end in tl:
                gap = seg_start - prev_end
                if gap > self.MAX_GAP:
                    mid = (prev_end + seg_start) / 2
                    # Find best scene covering the midpoint
                    target = None
                    for sc in scenes:
                        ss = float(sc.get("start_time", 0))
                        se = float(sc.get("end_time", ss + 30))
                        if ss <= mid <= se:
                            target = sc
                            break
                    if target and target.get("_brain", {}).get("decision") != "avatar_only":
                        sc_start = float(target.get("start_time", 0))
                        offset   = max(0.0, mid - sc_start - 1.5)
                        prefer   = target.get("_brain", {}).get("media_type", "image")
                        dur      = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
                        ok = self._inject_media(target, media_dir, used_urls,
                                                offset=offset, clip_dur=dur,
                                                label=f"gap{int(mid)}",
                                                prefer_type=prefer)
                        if ok:
                            gap_fixed = True
                            break
                prev_end = max(prev_end, seg_end)

            # Also check final trailing gap
            if not gap_fixed:
                if duration - prev_end > self.MAX_GAP:
                    # Find last scene
                    for sc in reversed(scenes):
                        if sc.get("_brain", {}).get("decision") != "avatar_only":
                            sc_start = float(sc.get("start_time", 0))
                            sc_dur   = float(sc.get("duration_seconds", 30))
                            offset   = sc_dur * 0.6
                            prefer   = sc.get("_brain", {}).get("media_type", "image")
                            dur      = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
                            ok = self._inject_media(sc, media_dir, used_urls,
                                                    offset=offset, clip_dur=dur,
                                                    label=f"tail{int(prev_end)}",
                                                    prefer_type=prefer)
                            if ok:
                                gap_fixed = True
                            break

            if not gap_fixed:
                break
            iters += 1

        # ── 3. Coverage enforcement (must reach MIN_COVERAGE) ────────────────
        # Keep trying ALL scenes (not just highest priority) until coverage met.
        # Allow avatar_only scenes to also get media if coverage is critically low.
        iters = 0
        consecutive_failures = 0
        while iters < max_iters:
            current = self._compute_coverage(plan)
            if current / max(duration, 1) >= self.MIN_COVERAGE:
                break

            if consecutive_failures >= 3:
                break   # tried many times with no success — stop

            # Try all non-avatar scenes, cycling through them
            all_eligible = sorted(
                [s for s in scenes
                 if s.get("_brain", {}).get("decision") != "avatar_only"],
                key=lambda s: s.get("_brain", {}).get("media_priority", 0),
                reverse=True,
            )
            # If still not enough, also allow ANY scene
            if not all_eligible or (current / max(duration, 1) < self.MIN_COVERAGE * 0.5):
                all_eligible = list(scenes)

            placed = False
            for sc in all_eligible:
                sc_dur  = float(sc.get("duration_seconds", 30))
                n_have  = len([m for m in sc.get("selected_media", []) if m.get("local_path")])
                # Allow one insert per 8s of scene duration
                max_here = max(1, int(sc_dur / 8))
                if n_have >= max_here:
                    continue
                prefer = sc.get("_brain", {}).get("media_type", "image")
                if not prefer or prefer == "none":
                    prefer = "image"
                dur    = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
                offset = min((n_have + 1) * (sc_dur / (max_here + 1)), sc_dur - dur - 1)
                offset = max(0.0, offset)
                ok = self._inject_media(sc, media_dir, used_urls,
                                        offset=offset, clip_dur=dur,
                                        label=f"cov{sc.get('scene_id','x')}_{n_have}",
                                        prefer_type=prefer)
                if ok:
                    placed = True
                    consecutive_failures = 0
                    break

            if not placed:
                consecutive_failures += 1
            iters += 1

        return plan

    def _find_best_media(
        self,
        queries:    List[str],
        media_type: str,
        media_dir:  Path,
        used_urls:  set,
        scene_id:   int,
    ) -> Optional[Dict]:
        """
        Core smart search:
         - Runs every query through every available API
         - Brave/Serper searched FIRST (richer web coverage)
         - Query-rank bonus applied so specific queries win
         - Video scenes prefer videos; image scenes prefer images
         - Tries up to 8 download attempts before giving up
        """
        candidates: List[Dict] = []
        want_video = (media_type == "video")

        for q_idx, query in enumerate(queries[:6]):
            bonus = self._QUERY_BONUS[min(q_idx, len(self._QUERY_BONUS) - 1)]

            # ── BRAVE: images (direct downloadable URLs from the open web) ──
            if self.keys["brave_search"]:
                for item in self._search_brave_images(query):
                    item["score"] += bonus
                    candidates.append(item)

            # ── SERPER: Google Images proxy (direct image URLs) ──────────────
            if self.keys["serper"]:
                for item in self._search_serper_images(query):
                    item["score"] += bonus
                    candidates.append(item)

            # ── PEXELS: stock photos + videos (always reliable download) ─────
            if self.keys["pexels"]:
                # If scene wants video, search videos; also grab photos as fallback
                if want_video:
                    for item in self._search_pexels(query, "video"):
                        item["score"] += bonus + 10   # extra boost for exact type
                        candidates.append(item)
                for item in self._search_pexels(query, "image"):
                    item["score"] += bonus
                    candidates.append(item)

            # ── PIXABAY: stock photos + videos ───────────────────────────────
            if self.keys["pixabay"]:
                if want_video:
                    for item in self._search_pixabay(query, "video"):
                        item["score"] += bonus + 10
                        candidates.append(item)
                for item in self._search_pixabay(query, "image"):
                    item["score"] += bonus
                    candidates.append(item)

            # ── UNSPLASH: high-quality photos ────────────────────────────────
            if self.keys["unsplash"]:
                for item in self._search_unsplash(query):
                    item["score"] += bonus
                    candidates.append(item)

        if not candidates:
            print(f"   ⚠ scene {scene_id}: no candidates found for queries: {queries[:3]}")
            return None

        # Deduplicate by URL, remove already-used
        seen: set = set()
        unique = []
        for c in candidates:
            u = c.get("url", "")
            if u and u not in used_urls and u not in seen:
                seen.add(u)
                unique.append(c)

        if not unique:
            return None

        # Sort: videos first if wanted, then by score descending
        unique.sort(
            key=lambda x: (
                (1 if (x.get("type") == "video") == want_video else 0),
                x.get("score", 0),
            ),
            reverse=True,
        )

        # Try downloading top-N candidates until one works
        for candidate in unique[:8]:
            is_video   = candidate.get("type") == "video"
            ext        = ".mp4" if is_video else ".jpg"
            uid        = hashlib.md5(candidate["url"].encode()).hexdigest()[:10]
            local_path = media_dir / f"s{scene_id}_{uid}{ext}"

            # Cache hit: already downloaded in a previous attempt
            if local_path.exists() and local_path.stat().st_size > (100_000 if is_video else 15_000):
                if self._is_valid_media(local_path):
                    candidate["local_path"] = str(local_path)
                    return candidate
                else:
                    local_path.unlink(missing_ok=True)

            ok = self._download(candidate["url"], local_path)
            if ok:
                # Auto-detect real media type from what was actually downloaded
                detected = self._detect_media_type(local_path)
                if detected == "unknown":
                    local_path.unlink(missing_ok=True)
                    continue
                # Rename to correct extension if needed
                real_ext = ".mp4" if detected == "video" else self._real_img_ext(local_path)
                if local_path.suffix.lower() != real_ext:
                    new_path = local_path.with_suffix(real_ext)
                    local_path.rename(new_path)
                    local_path = new_path
                candidate["type"]       = detected
                candidate["local_path"] = str(local_path)
                print(f"   ✔ scene {scene_id} — {candidate['source']} {detected}"
                      f"  score={candidate['score']:.0f}"
                      f"  {candidate.get('width',0)}×{candidate.get('height',0)}")
                return candidate

        print(f"   ✗ scene {scene_id}: all {min(len(unique),8)} candidates failed")
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # PARALLEL WAVE SEARCH
    # ─────────────────────────────────────────────────────────────────────────

    def _parallel_search(self, query_waves: List[List[str]], media_type: str) -> List[Dict]:
        """
        Wave-based parallel search.  Wave 0 → 1 → 2.

        Wave 0 (entity/brand queries):
          Brave runs FIRST and ALONE — it has real-world brand images
          that stock APIs never have. If Brave finds 3+ good hits, skip
          stock APIs for wave 0.  Stock APIs run in parallel after Brave.

        Wave 1+ (visual/stock queries):
          All providers run in parallel. Early stop if 3+ strong hits.
        """
        want_video = (media_type == "video")
        k = self.keys

        # Stock providers — reliable downloads
        stock_video_providers = [
            ("pexels_v",  lambda q: self._search_pexels(q, "video")   if k["pexels"]   else []),
            ("pixabay_v", lambda q: self._search_pixabay(q, "video")  if k["pixabay"]  else []),
            ("coverr",    lambda q: self._search_coverr(q)            if k["coverr"]   else []),
            ("videvo",    lambda q: self._search_videvo(q)            if k["videvo"]   else []),
        ]
        stock_image_providers = [
            ("pexels_i",  lambda q: self._search_pexels(q, "image")   if k["pexels"]   else []),
            ("pixabay_i", lambda q: self._search_pixabay(q, "image")  if k["pixabay"]  else []),
            ("unsplash",  lambda q: self._search_unsplash(q)          if k["unsplash"] else []),
            ("google",    lambda q: self._search_google_images(q)     if k["gcs_key"]  else []),
        ]
        # Web search providers — best for specific brands/entities but unreliable download
        web_providers = [
            ("brave",  lambda q: self._search_brave_images(q)       if k["brave_search"] else []),
            ("serper", lambda q: self._search_serper_images(q)      if k["serper"]       else []),
        ]

        stock_providers = stock_video_providers if want_video else stock_image_providers
        # Also add stock images as fallback even for video searches
        all_providers  = stock_providers + web_providers
        if want_video:
            all_providers += stock_image_providers  # images as last fallback for video scenes

        all_candidates: List[Dict] = []
        seen_urls: set = set()

        for wave_idx, queries in enumerate(query_waves):
            if not queries:
                continue

            # ── Wave 0: entity queries — Brave FIRST ──────────────────────────
            if wave_idx == 0 and k["brave_search"]:
                # Run Brave synchronously first (it has brand-specific images)
                for q_idx, q in enumerate(queries[:3]):
                    bonus = self._QUERY_BONUS[min(q_idx, len(self._QUERY_BONUS) - 1)]
                    brave_hits = self._search_brave_images(q)
                    for item in brave_hits:
                        u = item.get("url", "")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            # Extra bonus for Brave hits on entity queries (real brands)
                            item["score"] = item.get("score", 0) + bonus + 15
                            all_candidates.append(item)

            # ── All providers in parallel ─────────────────────────────────────
            with ThreadPoolExecutor(max_workers=min(len(queries) * len(all_providers), 20)) as exe:
                futs: Dict[Future, int] = {}
                for q_idx, q in enumerate(queries[:4]):
                    bonus = self._QUERY_BONUS[min(q_idx, len(self._QUERY_BONUS) - 1)]
                    for _, fn in all_providers:
                        fut = exe.submit(fn, q)
                        futs[fut] = bonus

                for fut in as_completed(futs, timeout=self.SEARCH_TIMEOUT * 4):
                    bonus = futs[fut]
                    try:
                        for item in (fut.result(timeout=0) or []):
                            u = item.get("url", "")
                            if u and u not in seen_urls:
                                seen_urls.add(u)
                                item["score"] = item.get("score", 0) + bonus
                                all_candidates.append(item)
                    except Exception:
                        pass

            # Early stop: 5+ strong candidates (raised from 3 for better selection)
            good = sum(1 for c in all_candidates if c.get("score", 0) >= self.GOOD_SCORE_THRESH)
            if good >= 5:
                break

        return all_candidates

    def _download_best(
        self,
        candidates: List[Dict],
        media_dir: Path,
        scene_id: int,
    ) -> Optional[Dict]:
        """
        Try candidates in order (best score first) until one downloads successfully.
        Uses session URL cache to skip re-downloads.
        """
        # Try up to 12 candidates — web URLs (Brave/Serper) often fail hotlink protection
        # so we need a larger pool. Stock APIs (Pexels, Pixabay) are tried first by score.
        tried = 0
        for candidate in candidates[:12]:
            url = candidate.get("url", "")
            if not url:
                continue
            tried += 1

            # Session-level cache hit (same URL already on disk this run)
            if url in self._url_cache:
                cached = self._url_cache[url]
                if Path(cached).exists():
                    candidate["local_path"] = cached
                    return candidate

            is_video   = candidate.get("type") == "video"
            ext        = ".mp4" if is_video else ".jpg"
            uid        = hashlib.md5(url.encode()).hexdigest()[:10]
            local_path = media_dir / f"s{scene_id}_{uid}{ext}"

            # Disk cache hit (previous phase)
            if local_path.exists():
                sz = local_path.stat().st_size
                if sz > (100_000 if is_video else 15_000) and self._is_valid_media(local_path):
                    candidate["local_path"] = str(local_path)
                    self._url_cache[url]    = str(local_path)
                    return candidate
                local_path.unlink(missing_ok=True)

            ok = self._download(url, local_path)
            if not ok:
                continue

            detected = self._detect_media_type(local_path)
            if detected == "unknown":
                local_path.unlink(missing_ok=True)
                continue

            real_ext = ".mp4" if detected == "video" else self._real_img_ext(local_path)
            if local_path.suffix.lower() != real_ext:
                new_path = local_path.with_suffix(real_ext)
                local_path.rename(new_path)
                local_path = new_path

            candidate["type"]       = detected
            candidate["local_path"] = str(local_path)
            self._url_cache[url]    = str(local_path)
            src_label = candidate.get("source", "?")
            print(f"   ✔ scene {scene_id} — {src_label} {detected}"
                  f"  score={candidate.get('score', 0):.0f}"
                  f"  {candidate.get('width',0)}×{candidate.get('height',0)}")
            return candidate

        print(f"   ✗ scene {scene_id}: all {tried} candidates failed download")
        return None

    # ── Coverr ────────────────────────────────────────────────────────────────

    def _search_coverr(self, query: str) -> List[Dict]:
        key = self.keys["coverr"]
        if not key:
            return []
        results = []
        try:
            r = requests.get(
                "https://api.coverr.co/videos",
                params={"query": query, "per_page": 8},
                headers={"Authorization": f"Bearer {key}"},
                timeout=2,
            )
            if r.ok:
                for v in r.json().get("hits", []):
                    enc = v.get("encodings", {})
                    url = (enc.get("mp4", {}).get("url")
                           or enc.get("hd", {}).get("url")
                           or v.get("url", ""))
                    w   = int(v.get("width",  1920))
                    h   = int(v.get("height", 1080))
                    if url and w >= 1280:
                        results.append({
                            "type"  : "video",
                            "source": "coverr",
                            "url"   : url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, "video"),
                        })
        except Exception as e:
            print(f"   Coverr error: {e}")
        return results

    # ── Videvo ────────────────────────────────────────────────────────────────

    def _search_videvo(self, query: str) -> List[Dict]:
        key = self.keys["videvo"]
        if not key:
            return []
        results = []
        try:
            r = requests.get(
                "https://www.videvo.net/api/v1/search",
                params={"keyword": query, "type": "footage",
                        "page": 1, "per_page": 8},
                headers={"Authorization": f"Bearer {key}"},
                timeout=2,
            )
            if r.ok:
                for v in r.json().get("results", []):
                    url = v.get("video_url") or v.get("url", "")
                    w   = int(v.get("width",  1920))
                    h   = int(v.get("height", 1080))
                    if url and w >= 1280:
                        results.append({
                            "type"  : "video",
                            "source": "videvo",
                            "url"   : url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, "video"),
                        })
        except Exception as e:
            print(f"   Videvo error: {e}")
        return results

    # ── Google Custom Search Images ───────────────────────────────────────────

    def _search_google_images(self, query: str) -> List[Dict]:
        key = self.keys["gcs_key"]
        cx  = self.keys["gcs_cx"]
        if not key:
            return []
        results = []
        try:
            r = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key"       : key,
                    "cx"        : cx,
                    "q"         : query,
                    "searchType": "image",
                    "imgType"   : "photo",
                    "imgSize"   : "XLARGE",
                    "num"       : 8,
                },
                timeout=2,
            )
            if r.ok:
                for item in r.json().get("items", []):
                    img = item.get("image", {})
                    url = item.get("link", "")
                    w   = int(img.get("width",  0))
                    h   = int(img.get("height", 0))
                    if not url or w < 800:
                        continue
                    if h > 0 and w / h < 1.0:
                        continue   # skip portrait
                    results.append({
                        "type"  : "image",
                        "source": "google",
                        "url"   : url,
                        "width" : w or 1280,
                        "height": h or 720,
                        "score" : self._score(w or 1280, h or 720, "image"),
                    })
        except Exception as e:
            print(f"   Google CSE error: {e}")
        return results

    def _detect_media_type(self, path: Path) -> str:
        """Ask ffprobe what kind of media this file contains."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                          timeout=10).decode().strip().lower()
            if "video" in out:
                return "video"
            if "audio" in out:
                return "unknown"   # audio-only — skip
            # No streams but file exists → might be raw image (JPEG/PNG/WEBP)
            # ffprobe can't always decode images; try header magic bytes
            with open(path, "rb") as f:
                header = f.read(12)
            if (header[:3] == b"\xff\xd8\xff"           # JPEG
                    or header[:8] == b"\x89PNG\r\n\x1a\n"  # PNG
                    or header[:4] in (b"RIFF", b"WEBP")    # WEBP
                    or header[:6] in (b"GIF87a", b"GIF89a")  # GIF
                    or header[:2] in (b"BM",)):               # BMP
                return "image"
            return "unknown"
        except Exception:
            return "unknown"

    def _real_img_ext(self, path: Path) -> str:
        """Return the real image extension from magic bytes."""
        try:
            with open(path, "rb") as f:
                h = f.read(12)
            if h[:3] == b"\xff\xd8\xff":
                return ".jpg"
            if h[:8] == b"\x89PNG\r\n\x1a\n":
                return ".png"
            if b"WEBP" in h:
                return ".webp"
            if h[:6] in (b"GIF87a", b"GIF89a"):
                return ".gif"
        except Exception:
            pass
        return ".jpg"  # safe default

    # ── Brave Image Search ────────────────────────────────────────────────────
    # Returns direct image URLs from the open web — best for specific/niche topics.

    def _search_brave_images(self, query: str) -> List[Dict]:
        key = self.keys["brave_search"]
        if not key:
            return []
        results = []
        try:
            r = requests.get(
                "https://api.search.brave.com/res/v1/images/search",
                headers={
                    "Accept"              : "application/json",
                    "Accept-Encoding"     : "gzip",
                    "X-Subscription-Token": key,
                },
                params={"q": query, "count": 10, "safesearch": "off",
                        "search_lang": "en", "spellcheck": 1},
                timeout=2,
            )
            if r.ok:
                for item in r.json().get("results", []):
                    props = item.get("properties", {})
                    url   = props.get("url") or item.get("url", "")
                    w     = props.get("width",  0)
                    h     = props.get("height", 0)
                    # Skip tiny/portrait images
                    if not url or w < 800 or (h > 0 and w / h < 1.0):
                        continue
                    results.append({
                        "type"  : "image",
                        "source": "brave",
                        "url"   : url,
                        "width" : w or 1280,
                        "height": h or 720,
                        "score" : self._score(w or 1280, h or 720, "image"),
                    })
        except Exception as e:
            print(f"   Brave images error: {e}")
        return results

    # ── Serper Image Search ───────────────────────────────────────────────────
    # Google Images via Serper.dev — excellent keyword coverage.

    def _search_serper_images(self, query: str) -> List[Dict]:
        key = self.keys["serper"]
        if not key:
            return []
        results = []
        try:
            r = requests.post(
                "https://google.serper.dev/images",
                headers={"X-API-KEY": key, "Content-Type": "application/json"},
                json={"q": query, "num": 10},
                timeout=2,
            )
            if r.ok:
                for item in r.json().get("images", []):
                    url = item.get("imageUrl", "")
                    w   = item.get("imageWidth",  0)
                    h   = item.get("imageHeight", 0)
                    if not url or (w > 0 and w < 800):
                        continue
                    if h > 0 and w > 0 and w / h < 1.0:
                        continue  # skip portrait
                    results.append({
                        "type"  : "image",
                        "source": "serper",
                        "url"   : url,
                        "width" : w or 1280,
                        "height": h or 720,
                        "score" : self._score(w or 1280, h or 720, "image"),
                    })
        except Exception as e:
            print(f"   Serper images error: {e}")
        return results

    # ── Pexels ────────────────────────────────────────────────────────────────

    def _search_pexels(self, query: str, media_type: str) -> List[Dict]:
        key = self.keys["pexels"]
        if not key:
            return []
        results = []
        try:
            if media_type == "video":
                url = "https://api.pexels.com/videos/search"
                params = {"query": query, "per_page": 8,
                          "orientation": "landscape", "size": "large"}
                r = requests.get(url, headers={"Authorization": key},
                                 params=params, timeout=2)
                if r.ok:
                    for v in r.json().get("videos", []):
                        files = sorted(
                            [f for f in v.get("video_files", [])
                             if f.get("width", 0) >= 1280],
                            key=lambda f: f.get("width", 0), reverse=True
                        )
                        if not files:
                            files = v.get("video_files", [])
                        if files:
                            results.append({
                                "type"  : "video",
                                "source": "pexels",
                                "url"   : files[0]["link"],
                                "width" : files[0].get("width",  1920),
                                "height": files[0].get("height", 1080),
                                "score" : self._score(files[0].get("width", 0),
                                                      files[0].get("height", 0), "video"),
                            })
            else:
                url = "https://api.pexels.com/v1/search"
                params = {"query": query, "per_page": 8,
                          "orientation": "landscape", "size": "large"}
                r = requests.get(url, headers={"Authorization": key},
                                 params=params, timeout=2)
                if r.ok:
                    for p in r.json().get("photos", []):
                        src     = p.get("src", {})
                        img_url = (src.get("large2x") or src.get("large")
                                   or src.get("original"))
                        if img_url:
                            results.append({
                                "type"  : "image",
                                "source": "pexels",
                                "url"   : img_url,
                                "width" : p.get("width",  1920),
                                "height": p.get("height", 1080),
                                "score" : self._score(p.get("width", 0),
                                                      p.get("height", 0), "image"),
                            })
        except Exception as e:
            print(f"   Pexels error [{media_type}]: {e}")
        return results

    # ── Pixabay ───────────────────────────────────────────────────────────────

    def _search_pixabay(self, query: str, media_type: str) -> List[Dict]:
        key = self.keys["pixabay"]
        if not key:
            return []
        results = []
        try:
            if media_type == "video":
                url    = "https://pixabay.com/api/videos/"
                params = {"key": key, "q": query, "per_page": 8,
                          "video_type": "film", "min_width": 1280}
            else:
                url    = "https://pixabay.com/api/"
                params = {"key": key, "q": query, "per_page": 8,
                          "image_type": "photo", "orientation": "horizontal",
                          "min_width": 1280}
            r = requests.get(url, params=params, timeout=2)
            if r.ok:
                for item in r.json().get("hits", []):
                    if media_type == "video":
                        vids   = item.get("videos", {})
                        file   = (vids.get("large") or vids.get("medium")
                                  or vids.get("small") or {})
                        dl_url = file.get("url")
                        w, h   = file.get("width", 1280), file.get("height", 720)
                    else:
                        dl_url = (item.get("largeImageURL")
                                  or item.get("webformatURL"))
                        w, h   = (item.get("imageWidth",  1280),
                                  item.get("imageHeight", 720))
                    if dl_url:
                        results.append({
                            "type"  : "video" if media_type == "video" else "image",
                            "source": "pixabay",
                            "url"   : dl_url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, media_type),
                        })
        except Exception as e:
            print(f"   Pixabay error [{media_type}]: {e}")
        return results

    # ── Unsplash ──────────────────────────────────────────────────────────────

    def _search_unsplash(self, query: str) -> List[Dict]:
        key = self.keys["unsplash"]
        if not key:
            return []
        results = []
        try:
            r = requests.get(
                "https://api.unsplash.com/search/photos",
                headers={"Authorization": f"Client-ID {key}"},
                params={"query": query, "per_page": 8, "orientation": "landscape"},
                timeout=2,
            )
            if r.ok:
                for p in r.json().get("results", []):
                    urls    = p.get("urls", {})
                    img_url = urls.get("full") or urls.get("regular")
                    w, h    = p.get("width", 1920), p.get("height", 1080)
                    if img_url and w >= 1280:
                        results.append({
                            "type"  : "image",
                            "source": "unsplash",
                            "url"   : img_url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, "image"),
                        })
        except Exception as e:
            print(f"   Unsplash error: {e}")
        return results

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, w: int, h: int, media_type: str) -> float:
        """
        Base score (0–100) before query-rank bonus.
        Rewards 1080p+ landscape. Discards portrait.
        Videos get a +20 bonus over images (richer visual impact).
        """
        if w <= 0 or h <= 0:
            return 0.0
        res_score = min(w / 1920, 1.0) * 40
        ratio     = w / h
        if ratio < 1.0:
            ratio_score = 0        # portrait — never use
        elif 1.5 <= ratio <= 2.2:
            ratio_score = 40       # ideal 16:9
        elif 1.2 <= ratio < 1.5:
            ratio_score = 25       # 4:3 / slight landscape — acceptable
        else:
            ratio_score = 15       # ultra-wide or weird ratio
        type_bonus = 20 if media_type == "video" else 0
        return res_score + ratio_score + type_bonus

    # ── Downloader ────────────────────────────────────────────────────────────

    # Rotate real browser User-Agents to defeat hotlink protection
    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    ]
    _ua_idx: int = 0

    def _next_ua(self) -> str:
        ua = self._USER_AGENTS[self._ua_idx % len(self._USER_AGENTS)]
        self._ua_idx += 1
        return ua

    # MIME types we accept as valid media
    _VALID_IMAGE_MIME = {
        "image/jpeg", "image/jpg", "image/png", "image/webp",
        "image/gif", "image/bmp", "image/tiff",
    }
    _VALID_VIDEO_MIME = {
        "video/mp4", "video/mpeg", "video/webm", "video/quicktime",
        "video/x-msvideo", "video/x-matroska", "application/octet-stream",
    }

    def _download(self, url: str, dest: Path, timeout: int = 30,
                  retries: int = 2) -> bool:
        """
        Download url → dest with:
         - rotating User-Agent + Referer derived from url host
         - 3 retry attempts with 1s backoff
         - Content-Type guard: reject HTML/text responses (hotlink blocked)
         - Minimum size guard: images ≥ 15 KB, videos ≥ 100 KB
         - Final validation via ffprobe to confirm readable media
        """
        import urllib.parse as _up

        parsed  = _up.urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/"

        for attempt in range(retries):
            if dest.exists():
                dest.unlink()
            try:
                headers = {
                    "User-Agent"     : self._next_ua(),
                    "Referer"        : referer,
                    "Accept"         : "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection"     : "keep-alive",
                }
                r = requests.get(url, stream=True, timeout=timeout,
                                 headers=headers, allow_redirects=True)

                # Hard reject non-media content-type
                ct = r.headers.get("Content-Type", "").lower().split(";")[0].strip()
                if ct.startswith("text/") or ct in ("application/json",
                                                     "application/xml"):
                    print(f"   ✗ blocked [{ct}] {url[:70]}")
                    return False

                if not r.ok:
                    raise requests.HTTPError(f"HTTP {r.status_code}")

                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(65536):
                        if chunk:
                            fh.write(chunk)

                size = dest.stat().st_size
                # Minimum size checks
                is_video = dest.suffix.lower() == ".mp4"
                min_size = 100_000 if is_video else 15_000
                if size < min_size:
                    print(f"   ✗ too small ({size} B) {url[:70]}")
                    dest.unlink()
                    return False

                # Final sanity: ffprobe must read at least one stream
                if not self._is_valid_media(dest):
                    print(f"   ✗ ffprobe invalid {url[:70]}")
                    dest.unlink()
                    return False

                return True

            except Exception as e:
                print(f"   ✗ attempt {attempt+1}/{retries} — {url[:70]}: {e}")
                if dest.exists():
                    dest.unlink()
                if attempt < retries - 1:
                    time.sleep(1.0 * (attempt + 1))

        return False

    def _is_valid_media(self, path: Path) -> bool:
        """Return True if ffprobe can read at least one stream from path."""
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                          timeout=10).decode().strip()
            return bool(out)   # non-empty → valid
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3 — PRE-PROCESS CLIPS
    # ─────────────────────────────────────────────────────────────────────────

    def _preprocess_clips(
        self, plan: Dict, job_dir: Path, avatar_duration: float
    ) -> List[Dict]:
        """
        For every media insert, produce a 1920×1080 muted clip of exact duration.
        Clips are encoded in parallel (max 4 workers) for speed.
        Returns timeline list: [{start, end, clip_path}, …]
        """
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(exist_ok=True)

        # Collect all pending clip jobs first (for budget accounting)
        jobs = []
        broll_budget = avatar_duration * self.MAX_BROLL_COVERAGE
        broll_acc    = 0.0

        for scene in plan.get("scenes", []):
            scene_start = float(scene.get("start_time", 0))
            scene_end   = float(scene.get("end_time", scene_start + 30))

            for media in scene.get("selected_media", []):
                lp = media.get("local_path")
                if not lp or not Path(lp).exists():
                    continue

                insert_offset = float(media.get("insertion_offset", 0))
                clip_dur      = float(media.get("clip_duration", 7))

                start_t = min(scene_start + insert_offset, scene_end - clip_dur)
                start_t = max(start_t, scene_start)
                end_t   = min(start_t + clip_dur, scene_end, avatar_duration - 0.5)

                actual = end_t - start_t
                if actual < 2:
                    continue
                if broll_acc + actual > broll_budget:
                    continue

                broll_acc += actual
                out_clip   = clips_dir / f"clip_{scene['scene_id']}_{int(start_t)}.mp4"
                jobs.append({
                    "src"      : lp,
                    "dst"      : str(out_clip),
                    "duration" : actual,
                    "media_type": media.get("type", "image"),
                    "start_t"  : start_t,
                    "end_t"    : end_t,
                    "type"     : media.get("type"),
                    "source"   : media.get("source"),
                })

        if not jobs:
            return []

        # Parallel encode (max 4 workers — FFmpeg uses all cores internally)
        results: List[Dict] = []
        lock = threading.Lock()

        def _encode_job(job: Dict):
            ok = self._make_clip(job["src"], job["dst"],
                                 job["duration"], job["media_type"])
            if ok:
                with lock:
                    results.append({
                        "start"    : job["start_t"],
                        "end"      : job["end_t"],
                        "clip_path": job["dst"],
                        "type"     : job["type"],
                        "source"   : job["source"],
                    })

        with ThreadPoolExecutor(max_workers=4) as exe:
            futs = [exe.submit(_encode_job, j) for j in jobs]
            for f in as_completed(futs):
                try:
                    f.result()
                except Exception as exc:
                    print(f"   ✗ clip encode error: {exc}")

        # Sort by start time, remove overlaps
        results.sort(key=lambda x: x["start"])
        clean = []
        last_end = 0.0
        for item in results:
            if Path(item["clip_path"]).exists() and item["start"] >= last_end + 0.5:
                clean.append(item)
                last_end = item["end"]
        return clean

    def _make_clip(self, src: str, dst: str, duration: float, media_type: str) -> bool:
        """
        Produce a 1920×1080 muted H.264 clip of exact duration.
        Handles: JPEG, PNG, WEBP, GIF, MP4, MOV, WEBM, MKV, AVI, and anything
        else FFmpeg can decode. Re-detects media type from file if uncertain.
        """
        scale_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        )
        src_path = Path(src)

        # Re-detect actual type from file (Brave/Serper may serve WEBP as .jpg etc.)
        actual_type = self._detect_media_type(src_path)
        if actual_type == "unknown":
            print(f"   ✗ _make_clip: unreadable file {src}")
            return False

        if actual_type == "image":
            # Still image → clip: low framerate + tune stillimage = ultra fast encode
            ok = _run_ffmpeg([
                "-loop", "1",
                "-framerate", "2",          # 2 fps is enough for a static image
                "-i", src,
                "-vf", scale_filter,
                "-t", str(round(duration, 3)),
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
                "-crf", "35",               # higher CRF = faster + smaller for stills
                "-tune", "stillimage",      # FFmpeg stillimage tune = faster + sharper
                "-g", "600",                # long GOP, no need for keyframes in stills
                "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart",
                dst,
            ], label="img→clip")
            return ok

        else:  # video
            src_dur = _ffprobe_duration(src)
            if src_dur <= 0:
                print(f"   ✗ _make_clip: zero-duration video {src}")
                return False
            trim = min(duration, src_dur)

            # Re-encode with -ss 0 to handle odd container issues
            ok = _run_ffmpeg([
                "-ss", "0",
                "-i", src,
                "-t", str(round(trim, 3)),
                "-vf", scale_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "26",
                "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart",
                dst,
            ], label="vid→clip")

            if not ok:
                # Fallback: try with -vsync vfr for weird frame-rate videos
                ok = _run_ffmpeg([
                    "-i", src,
                    "-t", str(round(trim, 3)),
                    "-vf", scale_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "26",
                    "-pix_fmt", "yuv420p", "-vsync", "vfr", "-an",
                    "-movflags", "+faststart",
                    dst,
                ], label="vid→clip-vfr")
            return ok

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 4 — RENDER
    # ─────────────────────────────────────────────────────────────────────────

    def _render(self, avatar_path: str, timeline: List[Dict], out_path: str):
        """
        Build FFmpeg overlay command:
          - Avatar = base track (1920×1080, audio preserved)
          - Each timeline entry = overlay at [start, end)
          - All overlays are muted (pre-processed in Phase 3)

        For large timelines (>40 clips), batches are chained in groups
        to avoid hitting FFmpeg filter_complex node limits.
        """
        if not timeline:
            print("   ⚠️  No B-roll timeline — check if downloads succeeded. Rendering avatar-only.")
            self._progress(80, "No B-roll — encoding avatar only (check media API keys)")
            self._render_avatar_only(avatar_path, out_path)
            return

        # Filter out any clips that don't exist on disk (safety)
        timeline = [t for t in timeline if Path(t["clip_path"]).exists()
                    and Path(t["clip_path"]).stat().st_size > 1000]
        if not timeline:
            print("   ⚠️  All clips missing on disk after preprocessing — avatar-only fallback.")
            self._progress(80, "All clips missing — avatar-only output")
            self._render_avatar_only(avatar_path, out_path)
            return

        n = len(timeline)
        self._progress(76, f"Building FFmpeg overlay graph ({n} B-roll inserts)…")
        print(f"   📹 Rendering {n} B-roll clips into final video…")
        for i, t in enumerate(timeline[:5]):
            print(f"      clip {i+1}: start={t['start']:.1f}s  dur={t['end']-t['start']:.1f}s  {Path(t['clip_path']).name}")
        if n > 5:
            print(f"      … and {n-5} more clips")

        # ── Build inputs ──────────────────────────────────────────────────────
        inputs = ["-i", avatar_path]
        for item in timeline:
            inputs += ["-i", item["clip_path"]]

        # ── Build filter_complex ──────────────────────────────────────────────
        scale_base = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1[base]"
        )
        parts = [scale_base]

        prev = "base"
        for i, item in enumerate(timeline):
            idx     = i + 1
            s, e    = item["start"], item["end"]
            clbl    = f"c{idx}"
            out_lbl = f"v{idx}"
            parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,setsar=1[{clbl}]")
            parts.append(
                f"[{prev}][{clbl}]overlay="
                f"enable='between(t,{s:.3f},{e:.3f})':x=0:y=0[{out_lbl}]"
            )
            prev = out_lbl

        filter_complex = ";".join(parts)

        cmd = (
            inputs
            + ["-filter_complex", filter_complex]
            + ["-map", f"[{prev}]", "-map", "0:a?"]
            + ["-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "28"]
            + ["-c:a", "aac", "-b:a", "192k"]
            + ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            + [out_path]
        )

        self._progress(78, f"FFmpeg rendering {n} clips… (may take a few minutes for long videos)")
        ok = _run_ffmpeg(cmd, label="overlay-render")

        if not ok:
            print("   ⚠️  Overlay render failed — trying concat fallback…")
            # Second attempt: try with fewer clips (drop last 20% as safety)
            if len(timeline) > 5:
                reduced = timeline[:int(len(timeline) * 0.8)]
                self._progress(85, f"Retrying with {len(reduced)} clips…")
                ok2 = self._render_with_timeline(avatar_path, reduced, out_path)
                if ok2:
                    return
            self._progress(90, "Render failed — avatar-only fallback")
            self._render_avatar_only(avatar_path, out_path)

    def _render_with_timeline(self, avatar_path: str, timeline: List[Dict], out_path: str) -> bool:
        """Re-render with a given timeline. Returns True on success."""
        inputs = ["-i", avatar_path]
        for item in timeline:
            inputs += ["-i", item["clip_path"]]

        scale_base = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1[base]"
        )
        parts = [scale_base]
        prev = "base"
        for i, item in enumerate(timeline):
            idx, s, e = i + 1, item["start"], item["end"]
            clbl, out_lbl = f"c{idx}", f"v{idx}"
            parts.append(f"[{idx}:v]setpts=PTS-STARTPTS,setsar=1[{clbl}]")
            parts.append(f"[{prev}][{clbl}]overlay=enable='between(t,{s:.3f},{e:.3f})':x=0:y=0[{out_lbl}]")
            prev = out_lbl

        cmd = (
            inputs
            + ["-filter_complex", ";".join(parts)]
            + ["-map", f"[{prev}]", "-map", "0:a?"]
            + ["-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "28"]
            + ["-c:a", "aac", "-b:a", "192k"]
            + ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            + [out_path]
        )
        return _run_ffmpeg(cmd, label="overlay-render-retry")

    def _render_avatar_only(self, avatar_path: str, out_path: str):
        """Encode avatar to 1080p H.264 with no overlays."""
        _run_ffmpeg([
            "-i", avatar_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0", "-crf", "28",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out_path,
        ], label="avatar-only")



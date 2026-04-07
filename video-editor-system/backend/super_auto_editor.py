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


def _build_dec(decision: str, media_type: str, insert_count: int,
               rules: List[str]) -> Dict:
    """Construct a standardised decision dict for _media_decision_engine."""
    return {
        "decision"       : decision,
        "media_type"     : media_type,
        "insert_count"   : insert_count,
        "rules_triggered": rules,
        "debug_log"      : " | ".join(rules) if rules else "no rules triggered",
    }


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

    # ── Coverage / timing constants ───────────────────────────────────────────
    MAX_BROLL_COVERAGE = 0.75  # hard cap — never exceed 75%
    MIN_COVERAGE       = 0.50  # must reach at least 50% coverage
    MAX_COVERAGE       = 0.70  # target cap at 70%
    IMAGE_EXACT_DUR    = 3.0   # images ALWAYS exactly 3 s
    IMAGE_MAX_DUR      = 3.0   # alias
    VIDEO_MIN_DUR      = 5.0   # videos at least 5 s
    VIDEO_MAX_DUR      = 10.0  # videos at most 10 s
    MIN_GAP            = 3.0   # min silence between inserts
    MAX_GAP            = 16.0  # max gap without media (hard rule)
    SEARCH_TIMEOUT     = 3.0   # per-provider HTTP timeout
    GOOD_SCORE_THRESH  = 55.0  # early-stop threshold

    # ── Layer 1: Scene Analysis thresholds ───────────────────────────────────
    # Motion words → motion_need_score
    # Static words → explanatory_score
    # Both feed visual_opportunity_score

    # ── Layer 2: Media Decision Engine thresholds ────────────────────────────
    MOTION_NEED_VIDEO_THR   = 65   # motion_need >= this  → prefer video
    ENTITY_SPEC_IMAGE_THR   = 60   # entity_specificity >= this + low motion → image
    IMPORTANCE_MIXED_THR    = 80   # importance >= this AND vos >= 70 → mixed
    TRANSITION_AVATAR_THR   = 70   # transition_score >= this AND vos < 40 → avatar_only
    LOW_VOS_AVATAR_THR      = 20   # visual_opportunity < this → avatar_only
    DENSITY_AVATAR_THR      = 0.85 # recent_density > this → force avatar_only breathing room

    # ── Layer 3 / Planner ────────────────────────────────────────────────────
    OPENING_DEADLINE       = 3.0   # media MUST appear by this second
    MAX_CONSECUTIVE_AVATAR = 3     # max avatar-only scenes in a row before forcing media

    # ── Candidate Ranking weights (11-category) ──────────────────────────────
    _RANK_W = {
        "entity_match"     : 2.0,
        "exact_match"      : 2.0,
        "scene_fit"        : 1.5,
        "resolution"       : 1.0,
        "aspect_ratio"     : 1.0,
        "source_priority"  : 0.8,
        "semantic_match"   : 0.7,
        "duration_fit"     : 0.5,
        "cinematic"        : 0.5,
        "uniqueness"       : 0.3,
        "quality"          : 0.3,
    }

    # Source quality ranking (higher = more reliable downloads)
    _SOURCE_PRIORITY = {
        "pexels"  : 10, "pixabay": 9, "coverr": 10, "videvo": 9,
        "unsplash": 8,  "google" : 7, "brave"  : 6,  "serper": 5,
    }

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

        prompt = f"""You are an elite AI documentary video editor and scene analyst with 20 years of experience.
Your task: deep analysis of this script to produce the most precise, visually-rich B-roll plan.

VIDEO DURATION: {duration_sec:.0f} seconds ({minutes:.1f} minutes)
SCRIPT LENGTH: {char_count:,} characters

TOTAL SCRIPT — READ EVERY WORD:
---
{script}
---

════════════ YOUR TASK ════════════
Produce a STRICT STRUCTURED SCENE PLAN with full scene analysis.
Think like the best YouTube documentary editor — every decision must be justified.
Every scene must have EXACT media matching what is being SAID in that moment.

════════════ SCENE SPLITTING RULES ════════════
- Split ONLY by real topic shift, story beat change, or emotional pivot
- Each scene: 20–120 seconds depending on content
- For a {minutes:.1f}-minute video: aim for {max(8, int(minutes*1.5))}-{max(15, int(minutes*3))} scenes
- Media must appear at least every 16 seconds somewhere in the video

════════════ SCENE SCORING RULES (REQUIRED for every scene) ════════════
For each scene you MUST compute these scores (0-100):
- visual_opportunity_score: how much visual content can this scene support?
- motion_need_score: does this scene REQUIRE moving footage to make sense?
- emotional_intensity_score: how emotionally intense or charged is this scene?
- explanatory_score: does this scene explain facts, data, or concepts with specific visuals?
- importance_score: how important is this scene to the overall narrative?
- transition_score: how much of this scene is connector/transition text with no visuals?

════════════ SCENE FLAGS (REQUIRED for every scene) ════════════
For each scene you MUST also set these boolean flags:
- has_brand: true if a real company/brand name is mentioned
- has_person: true if a real person name is mentioned
- has_place: true if a real location is mentioned
- has_product: true if a real product is mentioned
- has_historical_reference: true if the scene references a historical event or period
- has_process_or_action: true if the scene describes a process or visible action

════════════ MEDIA DECISION RULES ════════════
Use "avatar_only" ONLY when: transition_score > 70 AND visual_opportunity_score < 40
  OR scene is deeply personal with zero visual reference.
  Max 20% of scenes can be avatar_only.

  "image" → specific brand/person/product/place is mentioned AND motion is not required
  "video" → motion_need_score >= 65 OR scene describes movement, process, action
  "mixed" → 2 distinct visual moments (high importance + rich visual content)

CRITICAL: Media must match EXACTLY. "Apple released iPhone" → show iPhone, not generic tech.

════════════ ENTITY EXTRACTION (MOST IMPORTANT) ════════════
- brand_entities: Real company/brand names (e.g. "Apple", "Tesla", "Nike", "Ford")
- person_entities: Real people (e.g. "Elon Musk", "Steve Jobs")
- place_entities: Real locations (e.g. "Paris", "Wall Street", "Silicon Valley")
- product_entities: Real products (e.g. "iPhone 15", "Model S", "Air Max")
- brand_query: ONE precise search query using entity name + specific visual context
  Examples: "Apple iPhone 15 launch event product photo",
            "Ford factory assembly line production footage",
            "Elon Musk Tesla presentation stage"

════════════ SEARCH QUERIES RULES ════════════
- search_queries[0]: Most specific — use real brand/entity name + visual context
- search_queries[1]: Cinematic/documentary style (e.g. "cinematic factory footage")
- search_queries[2]: Conceptual match (e.g. "industrial production line workers")
- search_queries[3-5]: Broader fallback queries, still specific to THIS scene
- NEVER use: "car", "people", "technology", "business" alone — always add specifics

════════════ TIMING RULES ════════════
- Total timing must equal exactly {duration_sec:.0f} seconds
- Start times sequential, no overlap
- Proportional distribution: longer scenes for denser script sections

Return ONLY valid JSON (no markdown, no explanation):

{{
  "scenes": [
    {{
      "scene_id": 1,
      "title": "precise scene title",
      "summary": "one sentence — what is SAID in this scene specifically",
      "script_excerpt": "first 150 chars of this scene verbatim",
      "start_time": 0,
      "end_time": 45,
      "duration_seconds": 45,
      "tone": "informative|emotional|dramatic|energetic|neutral",
      "importance": "high|medium|low",
      "visual_richness": "rich|moderate|sparse",
      "decision": "avatar_only|image|video|mixed",
      "visual_opportunity_score": 72,
      "motion_need_score": 45,
      "emotional_intensity_score": 30,
      "explanatory_score": 60,
      "importance_score": 75,
      "transition_score": 10,
      "has_brand": true,
      "has_person": false,
      "has_place": true,
      "has_product": true,
      "has_historical_reference": false,
      "has_process_or_action": false,
      "brand_entities": ["Apple"],
      "person_entities": [],
      "place_entities": ["Silicon Valley"],
      "product_entities": ["iPhone 15"],
      "brand_query": "Apple iPhone 15 launch event product close-up",
      "search_queries": [
        "Apple iPhone 15 product display close-up",
        "cinematic smartphone launch event stage",
        "tech product reveal keynote footage",
        "Silicon Valley tech campus aerial view"
      ],
      "media_type_preferred": "image",
      "insertion_points": [
        {{
          "placement": "start|middle|end",
          "offset_from_scene_start": 5,
          "duration": 7,
          "reason": "exact reason why this media at this moment"
        }}
      ],
      "editor_notes": "what visual exactly should appear"
    }}
  ],
  "total_duration": {duration_sec:.0f},
  "pacing_notes": "overall visual pacing assessment"
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

        # Attach defaults for all required fields
        for scene in plan.get("scenes", []):
            scene.setdefault("selected_media", [])
            scene.setdefault("brand_entities", [])
            scene.setdefault("person_entities", [])
            scene.setdefault("place_entities", [])
            scene.setdefault("product_entities", [])
            scene.setdefault("brand_query", "")
            # Score fields (Gemini may not always fill these)
            scene.setdefault("visual_opportunity_score", None)  # None = compute locally
            scene.setdefault("motion_need_score", None)
            scene.setdefault("emotional_intensity_score", None)
            scene.setdefault("explanatory_score", None)
            scene.setdefault("importance_score", None)
            scene.setdefault("transition_score", None)
            # Flag fields
            scene.setdefault("has_brand", bool(scene.get("brand_entities")))
            scene.setdefault("has_person", bool(scene.get("person_entities")))
            scene.setdefault("has_place", bool(scene.get("place_entities")))
            scene.setdefault("has_product", bool(scene.get("product_entities")))
            scene.setdefault("has_historical_reference", False)
            scene.setdefault("has_process_or_action", False)

        return plan

    # =========================================================================
    # PHASE 2 — 4-LAYER MEDIA INTELLIGENCE ENGINE
    #
    # Layer 1: Scene Analysis Engine   — 6 scores + 6 flags per scene
    # Layer 2: Media Decision Engine   — strict rule-based decision + debug log
    # Layer 3: Global Timeline Planner — pre-plan coverage slots across timeline
    # Layer 4: Repair Engine           — mandatory second pass fixing violations
    # =========================================================================

    # Query-rank score bonuses (most specific query = highest bonus)
    _QUERY_BONUS = [30, 22, 14, 8, 3, 0]

    def _search_and_download(self, plan: Dict, job_dir: Path) -> Dict:
        """
        4-Layer Media Intelligence Engine.
        L1 Scene Analysis → L2 Decision → L3 Global Planner → L4 Repair Engine.
        """
        media_dir = job_dir / "media"
        media_dir.mkdir(exist_ok=True)
        used_urls: set = set()

        scenes   = plan.get("scenes", [])
        n        = len(scenes)
        duration = float(plan.get("total_duration", 0)) or sum(
            float(s.get("duration_seconds", 30)) for s in scenes
        )

        apis_lbl = self._available_api_labels()
        self._progress(28, f"APIs: [{apis_lbl}]  |  Duration: {duration:.0f}s")

        # ═══ LAYER 1: Scene Analysis Engine ═══════════════════════════════════
        self._progress(29, "Layer 1: Scene Analysis Engine…")
        for scene in scenes:
            scene["_analysis"] = self._scene_analysis_engine(scene)

        # ═══ LAYER 2: Media Decision Engine ════════════════════════════════════
        self._progress(30, "Layer 2: Media Decision Engine — applying rules…")
        consec_avatar = 0
        for scene in scenes:
            force = (consec_avatar >= self.MAX_CONSECUTIVE_AVATAR)
            dec   = self._media_decision_engine(scene, scene["_analysis"], force_media=force)
            scene["_decision"] = dec
            consec_avatar = 0 if dec["decision"] != "avatar_only" else consec_avatar + 1
            print(f"   [L2] Scene {scene.get('scene_id','?')} "
                  f"«{scene.get('title','')[:30]}»  "
                  f"→ {dec['decision']}  {dec['media_type']}  {dec['debug_log']}")

        # ═══ LAYER 3: Global Timeline Planner ══════════════════════════════════
        self._progress(32, "Layer 3: Global Timeline Planner — building coverage slots…")
        timeline_slots = self._global_timeline_planner(scenes, duration)
        print(f"   [L3] {len(timeline_slots)} slots planned "
              f"(target ≥{self.MIN_COVERAGE*100:.0f}% coverage)")

        inserts_placed = 0
        broll_seconds  = 0.0
        last_media_end = 0.0

        # ── PARALLEL SEARCH: search all slots simultaneously ──────────────────
        # This is the biggest speed win. Instead of searching slot-by-slot (each
        # blocking for 5-15s), we fire all searches in parallel and collect results.
        self._progress(33, f"[L3] Searching {len(timeline_slots)} slots in parallel…")

        def _search_slot(args):
            slot_i, slot = args
            scene       = slot["scene"]
            decision    = scene.get("_decision", {})
            wt          = slot.get("media_type") or decision.get("media_type") or "image"
            if wt == "none":
                wt = "image"
            waves      = self._build_query_waves(scene, wt)
            candidates = self._parallel_search(waves, wt)
            if not candidates and wt == "video":
                candidates = self._parallel_search(waves, "image")
                wt = "image"
            # Rank
            if candidates:
                candidates = [c for c in candidates
                              if c.get("url") not in used_urls]
                candidates = self._rank_candidates(
                    candidates, scene, scene.get("_analysis", {}), wt)
            return slot_i, slot, wt, candidates

        n_workers = min(len(timeline_slots), 16)
        search_results: List[tuple] = []
        with ThreadPoolExecutor(max_workers=n_workers) as exe:
            for res in exe.map(_search_slot, enumerate(timeline_slots),
                               timeout=self.SEARCH_TIMEOUT * 12):
                search_results.append(res)

        self._progress(46, f"[L3] Search done — downloading in parallel…")

        # ── PARALLEL DOWNLOAD: download best candidate for each slot ─────────
        # Downloads top candidates in parallel (up to 8 simultaneous downloads).
        download_lock = threading.Lock()

        def _download_slot(args):
            slot_i, slot, wt, candidates = args
            if not candidates:
                return slot_i, slot, wt, None
            sid = slot["scene"].get("scene_id", f"s{slot_i}")
            dl = self._download_parallel(candidates[:10], media_dir, sid)
            return slot_i, slot, wt, dl

        n_dl_workers = min(len(search_results), 8)
        download_results = []
        with ThreadPoolExecutor(max_workers=n_dl_workers) as exe:
            for res in exe.map(_download_slot, search_results,
                               timeout=60):
                download_results.append(res)

        # ── Assemble timeline from download results (sequential, instant) ─────
        # Sort by slot start time so timing guards work correctly
        def _slot_abs_start(r):
            s = r[1]["scene"]
            return float(s.get("start_time", 0)) + r[1]["offset"]
        download_results.sort(key=_slot_abs_start)

        for slot_i, slot, wt, dl in download_results:
            if not dl:
                print(f"   [L3] ✗ slot {slot_i+1}: no download")
                continue

            scene       = slot["scene"]
            scene_start = float(scene.get("start_time", 0))
            scene_end   = float(scene.get("end_time", scene_start + 30))
            offset      = slot["offset"]
            clip_dur    = slot["duration"]
            start_t     = scene_start + offset
            end_t       = min(start_t + clip_dur, scene_end, duration - 0.5)
            actual      = end_t - start_t

            if actual < 1.5:
                continue
            if start_t < last_media_end + self.MIN_GAP:
                continue
            if broll_seconds + actual > duration * self.MAX_COVERAGE:
                break

            # Fix duration to actual media type
            actual_type = dl.get("type", wt)
            if actual_type == "image":
                clip_dur = self.IMAGE_EXACT_DUR
            else:
                clip_dur = max(min(clip_dur, self.VIDEO_MAX_DUR), self.VIDEO_MIN_DUR)
            end_t  = min(start_t + clip_dur, scene_end, duration - 0.5)
            actual = end_t - start_t

            dl["insertion_offset"] = offset
            dl["clip_duration"]    = actual
            dl["placement"]        = slot.get("placement", "middle")
            scene.setdefault("selected_media", []).append(dl)
            used_urls.add(dl["url"])
            last_media_end  = end_t
            broll_seconds  += actual
            inserts_placed += 1
            print(f"   [L3] ✔ slot {slot_i+1} — {dl.get('source','?')} "
                  f"{actual_type} at t={start_t:.1f}s  "
                  f"score={dl.get('final_score', dl.get('score',0)):.0f}")

        coverage = broll_seconds / max(duration, 1) * 100
        self._progress(55, f"Layer 3 done — {inserts_placed} inserts  "
                           f"coverage={coverage:.0f}%")

        # ═══ LAYER 4: Repair Engine ════════════════════════════════════════════
        self._progress(56, "Layer 4: Repair Engine — fixing violations…")
        plan = self._repair_engine(plan, media_dir, used_urls, duration)

        final_cov = self._compute_coverage(plan) / max(duration, 1) * 100
        self._progress(58, f"Intelligence engine done — coverage {final_cov:.0f}%  "
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

    # =========================================================================
    # WORD LEXICONS — used by Scene Analysis Engine
    # =========================================================================

    _MOTION_WORDS = {
        "action","drive","run","walk","build","grow","move","fly","crash","fight",
        "swim","race","work","create","manufacture","produce","travel","climb","fall",
        "rise","flow","explode","launch","rush","evolve","transform","spread","attack",
        "march","celebrate","dance","compete","parade","fire","burn","flood","charge",
        "protest","battle","war","storm","wave","speed","jump","leap","operate",
        "assemble","deploy","install","roll","pull","push","carry","lift","throw",
        "drill","cut","weld","pour","mix","spin","rotate","activate","power",
    }
    _STATIC_WORDS = {
        "show","display","compare","define","explain","chart","logo","brand","person",
        "portrait","face","map","graph","data","statistics","product","object",
        "building","monument","symbol","document","certificate","flag","icon",
        "screen","interface","photo","image","picture","diagram","infographic",
        "label","design","model","render","blueprint","illustration","artwork",
    }
    _EMOTIONAL_WORDS = {
        "love","fear","hope","joy","pain","success","failure","dream","struggle",
        "victory","loss","grief","pride","anger","passion","inspiration","motivation",
        "courage","sacrifice","betrayal","emotion","feeling","heart","soul",
        "tears","happiness","sadness","triumph","despair","longing","nostalgia",
    }
    _DOCUMENTARY_WORDS = {
        "history","historical","war","factory","city","nature","documentary","archive",
        "archival","vintage","classic","era","period","decade","century","event",
        "revolution","movement","discovery","invention","industrial","ancient",
        "founded","established","origins","legacy","tradition","heritage","iconic",
    }
    _TRANSITION_WORDS = {
        "now","next","so","but","therefore","however","meanwhile","finally","also",
        "remember","consider","think","imagine","let","as","while","although",
        "anyway","moving","speaking","turning","today","yesterday","simply","basically",
    }
    _PROCESS_WORDS = {
        "step","process","how","method","technique","procedure","system","workflow",
        "install","configure","setup","build","deploy","create","generate","develop",
        "manufacture","assemble","produce","operate","run","execute","perform",
    }

    # =========================================================================
    # LAYER 1: SCENE ANALYSIS ENGINE
    # =========================================================================

    def _scene_analysis_engine(self, scene: Dict) -> Dict:
        """
        Layer 1: Compute 6 quantitative scores + 6 binary flags per scene.
        Uses Gemini-provided scores when present; falls back to local NLP otherwise.
        """
        text = (
            scene.get("title", "") + " " +
            scene.get("summary", "") + " " +
            scene.get("script_excerpt", "")
        ).lower()
        words = set(re.findall(r"\b\w+\b", text))
        dur   = float(scene.get("duration_seconds", 30))

        # ── Local NLP word-hit counts ─────────────────────────────────────────
        motion_hits      = len(words & self._MOTION_WORDS)
        static_hits      = len(words & self._STATIC_WORDS)
        emotional_hits   = len(words & self._EMOTIONAL_WORDS)
        documentary_hits = len(words & self._DOCUMENTARY_WORDS)
        transition_hits  = len(words & self._TRANSITION_WORDS)
        process_hits     = len(words & self._PROCESS_WORDS)

        # ── 6 Scores (use Gemini value if it provided it, else compute) ───────
        def _gem(key: str, default: float) -> float:
            v = scene.get(key)
            if v is not None and isinstance(v, (int, float)):
                return float(v)
            return default

        # 1. visual_opportunity_score — how much visual content can this scene hold
        vos_local = min(100, motion_hits*18 + static_hits*12 + documentary_hits*15)
        visual_opportunity_score = _gem("visual_opportunity_score", vos_local)

        # 2. motion_need_score — does this scene require movement to make sense
        mns_local = min(100, motion_hits * 22 + process_hits * 14)
        motion_need_score = _gem("motion_need_score", mns_local)

        # 3. emotional_intensity_score
        eis_local = min(100, emotional_hits * 25)
        emotional_intensity_score = _gem("emotional_intensity_score", eis_local)

        # 4. explanatory_score — explains facts/data/products/brands
        exs_local = min(100, static_hits * 18)
        explanatory_score = _gem("explanatory_score", exs_local)

        # 5. importance_score — scene importance to narrative
        imp_map = {"high": 85, "medium": 55, "low": 22}
        rich_map = {"rich": 80, "moderate": 55, "sparse": 20}
        imp  = imp_map.get(scene.get("importance", "medium"), 55)
        rich = rich_map.get(scene.get("visual_richness", "moderate"), 55)
        imp_local = imp * 0.65 + rich * 0.35
        importance_score = _gem("importance_score", imp_local)

        # 6. transition_score — how much of the scene is connector/filler text
        is_filler = (motion_hits == 0 and static_hits == 0 and dur < 20)
        ts_local  = min(100, transition_hits * 20) if is_filler else min(40, transition_hits*10)
        transition_score = _gem("transition_score", ts_local)

        # ── Flags ─────────────────────────────────────────────────────────────
        has_brand               = bool(scene.get("has_brand") or scene.get("brand_entities"))
        has_person              = bool(scene.get("has_person") or scene.get("person_entities"))
        has_place               = bool(scene.get("has_place") or scene.get("place_entities"))
        has_product             = bool(scene.get("has_product") or scene.get("product_entities"))
        has_historical_ref      = bool(scene.get("has_historical_reference") or documentary_hits >= 2)
        has_process_or_action   = bool(scene.get("has_process_or_action") or
                                       motion_hits >= 2 or process_hits >= 2)

        # Entity specificity: 0-100 (more named entities → higher specificity)
        entity_count = (
            len(scene.get("brand_entities",   [])) +
            len(scene.get("person_entities",  [])) +
            len(scene.get("place_entities",   [])) +
            len(scene.get("product_entities", []))
        )
        entity_specificity = min(100, entity_count * 30)

        return {
            "visual_opportunity_score"  : visual_opportunity_score,
            "motion_need_score"         : motion_need_score,
            "emotional_intensity_score" : emotional_intensity_score,
            "explanatory_score"         : explanatory_score,
            "importance_score"          : importance_score,
            "transition_score"          : transition_score,
            "has_brand"                 : has_brand,
            "has_person"                : has_person,
            "has_place"                 : has_place,
            "has_product"               : has_product,
            "has_historical_reference"  : has_historical_ref,
            "has_process_or_action"     : has_process_or_action,
            "entity_specificity"        : entity_specificity,
            "entity_count"              : entity_count,
            "_motion_hits"              : motion_hits,
            "_static_hits"              : static_hits,
        }

    # =========================================================================
    # LAYER 2: MEDIA DECISION ENGINE
    # =========================================================================

    def _media_decision_engine(self, scene: Dict, analysis: Dict,
                                force_media: bool = False) -> Dict:
        """
        Layer 2: Strict rule-based decision.  Every rule is logged.

        Rules (applied in order, first match wins):
          RULE_1  transition_score>70 AND visual_opportunity<40  → avatar_only
          RULE_2  entity_specificity>=60 AND motion_need<40      → image (exact match)
          RULE_3  motion_need>=65                                 → video
          RULE_4  has_historical_reference                        → video (archival)
          RULE_5  importance>=80 AND visual_opportunity>=70       → mixed (2 inserts)
          RULE_6  has_brand OR has_product OR has_person          → image (exact match)
          RULE_7  visual_opportunity>=30                          → image (generic)
          RULE_8  fallback                                        → avatar_only
        """
        vos = analysis["visual_opportunity_score"]
        mns = analysis["motion_need_score"]
        imp = analysis["importance_score"]
        ts  = analysis["transition_score"]
        es  = analysis["entity_specificity"]
        dur = float(scene.get("duration_seconds", 30))

        rules_triggered: List[str] = []

        # force_media: consecutive avatar scenes exceeded MAX_CONSECUTIVE_AVATAR
        if force_media:
            rules_triggered.append("FORCE: too many consecutive avatar scenes → override")
            media_type   = "image"
            decision     = "image_support"
            insert_count = 1
            return _build_dec(decision, media_type, insert_count, rules_triggered)

        # RULE 1: Pure transition / connector — no visual value
        if ts > self.TRANSITION_AVATAR_THR and vos < 40:
            rules_triggered.append(
                f"RULE_1: transition_score={ts:.0f}>{self.TRANSITION_AVATAR_THR}"
                f" AND visual_opportunity={vos:.0f}<40 → avatar_only"
            )
            return _build_dec("avatar_only", "none", 0, rules_triggered)

        # RULE 2: Named entity + low motion → exact image (brand/product/person)
        if es >= self.ENTITY_SPEC_IMAGE_THR and mns < 40:
            rules_triggered.append(
                f"RULE_2: entity_specificity={es:.0f}>={self.ENTITY_SPEC_IMAGE_THR}"
                f" AND motion_need={mns:.0f}<40 → image (exact entity match)"
            )
            return _build_dec("image_support", "image",
                              2 if imp >= 70 and dur >= 30 else 1, rules_triggered)

        # RULE 3: Motion-heavy scene — needs real footage
        if mns >= self.MOTION_NEED_VIDEO_THR:
            rules_triggered.append(
                f"RULE_3: motion_need={mns:.0f}>={self.MOTION_NEED_VIDEO_THR} → video"
            )
            return _build_dec("video_support", "video",
                              2 if imp >= 70 and dur >= 40 else 1, rules_triggered)

        # RULE 4: Historical / documentary content → archival footage
        if analysis["has_historical_reference"]:
            rules_triggered.append("RULE_4: has_historical_reference → video (archival)")
            return _build_dec("video_support", "video", 1, rules_triggered)

        # RULE 5: Very important + very visual → mixed (2 inserts)
        if imp >= self.IMPORTANCE_MIXED_THR and vos >= 70:
            rules_triggered.append(
                f"RULE_5: importance={imp:.0f}>={self.IMPORTANCE_MIXED_THR}"
                f" AND visual_opportunity={vos:.0f}>=70 → mixed"
            )
            media_type = "video" if mns >= 40 else "image"
            return _build_dec("mixed", media_type, 2, rules_triggered)

        # RULE 6: Has specific brand / product / person → image (exact match)
        if analysis["has_brand"] or analysis["has_product"] or analysis["has_person"]:
            rules_triggered.append(
                "RULE_6: has_brand/product/person → image (exact entity match)"
            )
            return _build_dec("image_support", "image", 1, rules_triggered)

        # RULE 7: Enough visual opportunity → image (generic stock)
        if vos >= self.LOW_VOS_AVATAR_THR:
            rules_triggered.append(
                f"RULE_7: visual_opportunity={vos:.0f}>={self.LOW_VOS_AVATAR_THR}"
                f" → image (generic)"
            )
            return _build_dec("image_support", "image", 1, rules_triggered)

        # RULE 8: Fallback — nothing visual here
        rules_triggered.append(
            f"RULE_8: visual_opportunity={vos:.0f}<{self.LOW_VOS_AVATAR_THR}"
            f" → avatar_only (no visual value)"
        )
        return _build_dec("avatar_only", "none", 0, rules_triggered)

    # =========================================================================
    # LAYER 3: GLOBAL TIMELINE PLANNER
    # =========================================================================

    def _global_timeline_planner(self, scenes: List[Dict], duration: float) -> List[Dict]:
        """
        Layer 3: Pre-plan media slots across the ENTIRE timeline before searching.

        Algorithm:
          1. Compute how many slots needed to hit MIN_COVERAGE
          2. Mark mandatory enforcement points (opening, every MAX_GAP interval)
          3. For every enforcement point, find the best candidate scene
          4. Fill remaining capacity with highest-priority eligible scenes
          5. Return ordered slot list [{scene, offset, duration, media_type, placement}]

        This guarantees MIN_COVERAGE and MAX_GAP structurally — not as an afterthought.
        """
        slots: List[Dict] = []
        # average slot duration: mix of 3s images and 7.5s videos ≈ 5.5s
        avg_slot_dur = 5.5
        target_secs  = duration * self.MIN_COVERAGE
        target_slots = max(4, int(target_secs / avg_slot_dur))

        # ── Step 1: Mark mandatory enforcement points ─────────────────────────
        # Opening (must have media in first 3 seconds)
        # Then every MAX_GAP seconds after last media end
        enforcement_times: List[float] = [0.0]  # opening
        t = self.MAX_GAP
        while t < duration - 3.0:
            enforcement_times.append(t)
            t += self.MAX_GAP

        # ── Step 2: Build priority map {scene_id → priority_score} ───────────
        # Higher priority = gets slots first
        def _priority(sc: Dict) -> float:
            dec = sc.get("_decision", {})
            ana = sc.get("_analysis", {})
            if dec.get("decision") == "avatar_only":
                return 0.0
            return (
                ana.get("importance_score", 50) * 0.4 +
                ana.get("visual_opportunity_score", 50) * 0.3 +
                ana.get("entity_specificity", 0) * 0.3
            )

        # ── Step 3: Assign enforcement slots ─────────────────────────────────
        used_scene_ids: set = set()   # scene_ids already assigned a slot

        for enforce_t in enforcement_times:
            if len(slots) >= target_slots:
                break
            # Find best scene covering or near this time
            best_sc = None
            best_pri = -1.0
            for sc in scenes:
                if sc.get("_decision", {}).get("decision") == "avatar_only":
                    continue
                ss = float(sc.get("start_time", 0))
                se = float(sc.get("end_time", ss + 30))
                if ss <= enforce_t <= se:
                    pri = _priority(sc)
                    if pri > best_pri:
                        best_pri = pri
                        best_sc  = sc
            # If no scene contains this point, pick nearest eligible scene
            if not best_sc:
                best_d = float("inf")
                for sc in scenes:
                    if sc.get("_decision", {}).get("decision") == "avatar_only":
                        continue
                    ss  = float(sc.get("start_time", 0))
                    se  = float(sc.get("end_time", ss + 30))
                    mid = (ss + se) / 2
                    d   = abs(mid - enforce_t)
                    if d < best_d:
                        best_d  = d
                        best_sc = sc
            if not best_sc:
                continue

            dec = best_sc.get("_decision", {})
            mt  = dec.get("media_type", "image")
            if mt == "none":
                mt = "image"
            dur_slot = self.IMAGE_EXACT_DUR if mt == "image" else 7.0

            ss     = float(best_sc.get("start_time", 0))
            se     = float(best_sc.get("end_time", ss + 30))
            offset = max(0.0, min(enforce_t - ss, se - ss - dur_slot - 0.5))

            slots.append({
                "scene"     : best_sc,
                "offset"    : offset,
                "duration"  : dur_slot,
                "media_type": mt,
                "placement" : "enforcement",
                "reason"    : f"enforce t={enforce_t:.0f}s gap/opening rule",
            })

        # ── Step 4: Fill remaining capacity with high-priority scenes ─────────
        sorted_scenes = sorted(scenes, key=_priority, reverse=True)
        for sc in sorted_scenes:
            if len(slots) >= target_slots * 2:   # max 2× target slots
                break
            dec = sc.get("_decision", {})
            if dec.get("decision") == "avatar_only":
                continue

            n_slots_this_scene = sum(1 for s in slots if s["scene"] is sc)
            sc_dur = float(sc.get("duration_seconds", 30))
            max_slots_for_scene = max(1, int(sc_dur / 8))
            if n_slots_this_scene >= max_slots_for_scene:
                continue

            mt       = dec.get("media_type", "image") or "image"
            dur_slot = self.IMAGE_EXACT_DUR if mt == "image" else 7.0
            ss       = float(sc.get("start_time", 0))
            sc_dur   = float(sc.get("duration_seconds", 30))

            # Place insert at an unoccupied position within the scene
            existing_offsets = [s["offset"] for s in slots if s["scene"] is sc]
            best_offset = None
            for candidate_offset in [sc_dur * 0.2, sc_dur * 0.5, sc_dur * 0.75, 0.5]:
                candidate_offset = min(candidate_offset, sc_dur - dur_slot - 0.5)
                candidate_offset = max(0.0, candidate_offset)
                too_close = any(abs(candidate_offset - eo) < self.MIN_GAP
                                for eo in existing_offsets)
                if not too_close:
                    best_offset = candidate_offset
                    break

            if best_offset is None:
                continue

            slots.append({
                "scene"     : sc,
                "offset"    : best_offset,
                "duration"  : dur_slot,
                "media_type": mt,
                "placement" : "priority_fill",
                "reason"    : f"priority={_priority(sc):.0f} fill",
            })

        # ── Step 5: Sort by absolute start time ──────────────────────────────
        def _slot_start(s: Dict) -> float:
            return float(s["scene"].get("start_time", 0)) + s["offset"]

        slots.sort(key=_slot_start)
        print(f"   [L3] Planner: {len(enforcement_times)} enforcement points, "
              f"{len(slots)} total slots, target={target_slots}")
        return slots

    # Common words to ignore when extracting fallback entities from text
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
        """Extract proper nouns from text. Used as fallback when Gemini entity fields empty."""
        words = re.findall(r"\b[A-Z][a-zA-Z]{1,30}\b", text)
        seen: set = set()
        entities: List[str] = []
        for w in words:
            if w.lower() not in self._ENTITY_STOPWORDS and w not in seen:
                seen.add(w)
                entities.append(w)
        return entities[:4]

    def _build_query_waves(self, scene: Dict, wanted_type: str = "image") -> List[List[str]]:
        """
        Entity-first query waves:
          Wave 0 — ENTITY-SPECIFIC: exact brand/person/product/place queries
                   (Brave searched FIRST on these — real-world brand imagery)
          Wave 1 — GEMINI's visual queries (stock API cinematic style)
          Wave 2 — Documentary/cinematic broad fallback
        """
        base         = scene.get("search_queries", [])
        brand_query  = scene.get("brand_query", "")
        title        = scene.get("title", "")
        summ         = scene.get("summary", "")
        excerpt      = scene.get("script_excerpt", "")

        brand_ents   = scene.get("brand_entities",   [])
        person_ents  = scene.get("person_entities",  [])
        place_ents   = scene.get("place_entities",   [])
        product_ents = scene.get("product_entities", [])
        all_entities = brand_ents + person_ents + place_ents + product_ents

        # Fallback entity extraction when Gemini didn't populate
        if not all_entities:
            all_entities = self._extract_entities(
                title + " " + summ + " " + excerpt[:200]
            )

        topic = title or summ[:60]
        media_hint = "footage" if wanted_type == "video" else "photo"

        # ── WAVE 0: Entity-specific — Brave + Serper run FIRST on these ────────
        # These queries target real brands, logos, characters, landmarks.
        # Brave/Serper have actual web images; stock APIs rarely have brand logos.
        wave0: List[str] = []

        if brand_query:
            wave0.append(brand_query)                      # Gemini's precise query

        # BRANDS → logo, official brand mark, headquarters
        for brand in brand_ents[:3]:
            if wanted_type == "image":
                wave0.append(f"{brand} logo official")     # brand mark / wordmark
                wave0.append(f"{brand} brand logo")
                wave0.append(f"{brand} official photo")
            else:
                wave0.append(f"{brand} footage official")
                wave0.append(f"{brand} commercial video")
                wave0.append(f"{brand} brand video")

        # PEOPLE → portrait, official photo, famous shot
        for person in person_ents[:2]:
            if wanted_type == "image":
                wave0.append(f"{person} official portrait photo")
                wave0.append(f"{person} face photo")
            else:
                wave0.append(f"{person} speech interview footage")
                wave0.append(f"{person} speaking video")

        # PLACES → landmark, aerial, iconic view
        for place in place_ents[:2]:
            if wanted_type == "image":
                wave0.append(f"{place} landmark photo")
                wave0.append(f"{place} famous view photo")
            else:
                wave0.append(f"{place} aerial footage")
                wave0.append(f"{place} cinematic footage")

        # PRODUCTS → product photo / closeup
        for product in product_ents[:2]:
            if wanted_type == "image":
                wave0.append(f"{product} official product photo")
                wave0.append(f"{product} closeup photo")
            else:
                wave0.append(f"{product} review footage")
                wave0.append(f"{product} video")

        # Deduplicate, limit to 8 (Brave runs on all of these)
        wave0 = list(dict.fromkeys(q for q in wave0 if q.strip()))[:8]

        # ── WAVE 1: Gemini's specific visual queries ──────────────────────────
        wave1 = list(dict.fromkeys(base[:5])) if base else [topic]

        # ── WAVE 2: Cinematic / documentary fallback ──────────────────────────
        wave2: List[str] = []
        for q in (base[:2] if base else [topic]):
            wave2.append(f"cinematic {q}")
        key_words = [w for w in topic.split() if len(w) > 4][:4]
        broad = " ".join(key_words) if key_words else topic
        if wanted_type == "video":
            wave2.append(f"documentary footage {broad}")
            wave2.append(f"4K cinematic {broad}")
        else:
            wave2.append(f"high quality {broad} photo")
            wave2.append(broad)
        wave2 = list(dict.fromkeys(q for q in wave2 if q.strip()))[:4]

        return [wave0, wave1, wave2]

    # =========================================================================
    # LAYER 4: REPAIR ENGINE (mandatory second pass)
    # =========================================================================

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
        analysis: Optional[Dict] = None,
    ) -> bool:
        """Search + download one media item and append it to scene['selected_media']."""
        waves      = self._build_query_waves(scene, prefer_type)
        candidates = self._parallel_search(waves, prefer_type)
        if not candidates and prefer_type == "video":
            candidates = self._parallel_search(waves, "image")
            prefer_type = "image"
        if not candidates:
            return False

        candidates = [c for c in candidates if c.get("url") not in used_urls]
        if not candidates:
            return False

        ana = analysis or scene.get("_analysis", {})
        candidates = self._rank_candidates(candidates, scene, ana, prefer_type)
        dl = self._download_best(candidates[:14], media_dir, label)
        if not dl:
            return False

        actual_type = dl.get("type", prefer_type)
        dur = self.IMAGE_EXACT_DUR if actual_type == "image" else clip_dur
        dl["insertion_offset"] = offset
        dl["clip_duration"]    = dur
        dl["placement"]        = "repair"
        scene.setdefault("selected_media", []).append(dl)
        used_urls.add(dl["url"])
        return True

    def _repair_engine(
        self,
        plan: Dict,
        media_dir: Path,
        used_urls: set,
        duration: float,
    ) -> Dict:
        """
        Layer 4: Mandatory repair pass. Detects and fixes ALL violations:
          V1. Boring opening — media must appear in first 3 seconds
          V2. Gaps > MAX_GAP (16s) — inject media into the gap
          V3. Trailing gap > MAX_GAP — inject at video tail
          V4. Coverage < MIN_COVERAGE (50%) — add more inserts
          V5. Too many consecutive avatar-only segments (enforced by planner, verified here)

        Runs up to 40 iterations total across all violation types.
        Stops only when all violations are cleared or no more media can be found.
        """
        scenes = plan.get("scenes", [])
        if not scenes:
            return plan

        def _rebuild_tl():
            return self._build_timeline_from_plan(plan)

        def _best_dec(sc: Dict) -> str:
            return sc.get("_decision", {}).get("media_type", "image") or "image"

        violations_fixed = {"opening": 0, "gap": 0, "coverage": 0}
        max_iters = 40

        # ── V1. Opening hook ──────────────────────────────────────────────────
        tl = _rebuild_tl()
        has_opening = bool(tl) and tl[0][0] <= self.OPENING_DEADLINE
        if not has_opening:
            first_sc = scenes[0]
            prefer   = _best_dec(first_sc)
            dur      = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
            ok = self._inject_media(
                first_sc, media_dir, used_urls,
                offset=0.0, clip_dur=dur,
                label="repair_opening", prefer_type=prefer,
                analysis=first_sc.get("_analysis"),
            )
            if ok:
                violations_fixed["opening"] += 1
                print(f"   [L4] ✓ Fixed V1 (opening hook injected)")
                tl = _rebuild_tl()
            else:
                print(f"   [L4] ✗ V1 unfixable (no media available for opening scene)")

        # ── V2. Gaps > MAX_GAP ────────────────────────────────────────────────
        for it in range(max_iters):
            tl       = _rebuild_tl()
            prev_end = 0.0
            gap_fixed = False

            # Check all gaps including trailing gap
            check_points = [(s, e) for s, e in tl] + [(duration, duration)]
            for seg_start, seg_end in check_points:
                gap = seg_start - prev_end
                if gap > self.MAX_GAP:
                    mid = (prev_end + seg_start) / 2
                    # Find best eligible scene covering midpoint
                    target_sc = None
                    best_pri  = -1.0
                    for sc in scenes:
                        ss  = float(sc.get("start_time", 0))
                        se  = float(sc.get("end_time",   ss + 30))
                        ana = sc.get("_analysis", {})
                        if ss <= mid <= se:
                            pri = ana.get("importance_score", 30)
                            if pri > best_pri:
                                best_pri = pri
                                target_sc = sc
                    # Fallback: nearest scene
                    if not target_sc:
                        best_d = float("inf")
                        for sc in scenes:
                            ss  = float(sc.get("start_time", 0))
                            se  = float(sc.get("end_time",   ss + 30))
                            mid_sc = (ss + se) / 2
                            d  = abs(mid_sc - mid)
                            if d < best_d:
                                best_d    = d
                                target_sc = sc
                    if target_sc:
                        sc_start = float(target_sc.get("start_time", 0))
                        sc_dur   = float(target_sc.get("duration_seconds", 30))
                        prefer   = _best_dec(target_sc)
                        dur_slot = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
                        offset   = max(0.0, min(mid - sc_start - 1.5,
                                                sc_dur - dur_slot - 0.5))
                        label    = f"repair_gap{int(mid)}"
                        ok = self._inject_media(
                            target_sc, media_dir, used_urls,
                            offset=offset, clip_dur=dur_slot,
                            label=label, prefer_type=prefer,
                            analysis=target_sc.get("_analysis"),
                        )
                        if ok:
                            gap_fixed = True
                            violations_fixed["gap"] += 1
                            print(f"   [L4] ✓ Fixed V2 (gap at t={mid:.0f}s, "
                                  f"scene «{target_sc.get('title','')[:25]}»)")
                            break
                prev_end = max(prev_end, seg_end)

            if not gap_fixed:
                break  # no more gaps to fix

        # ── V3+V4. Coverage enforcement ───────────────────────────────────────
        consecutive_fails = 0
        for it in range(max_iters):
            current_cov = self._compute_coverage(plan) / max(duration, 1)
            if current_cov >= self.MIN_COVERAGE:
                break
            if consecutive_fails >= 5:
                print(f"   [L4] ✗ Coverage stuck at {current_cov*100:.0f}% "
                      f"after {it} iters — stopping")
                break

            # Sort scenes by priority (most important first)
            eligible = sorted(
                [sc for sc in scenes
                 if sc.get("_decision", {}).get("decision") != "avatar_only"],
                key=lambda sc: sc.get("_analysis", {}).get("importance_score", 30),
                reverse=True,
            )
            if not eligible:
                eligible = list(scenes)

            placed = False
            for sc in eligible:
                sc_dur   = float(sc.get("duration_seconds", 30))
                n_have   = len([m for m in sc.get("selected_media", [])
                                if m.get("local_path")])
                max_here = max(1, int(sc_dur / 7))
                if n_have >= max_here:
                    continue

                prefer   = _best_dec(sc)
                dur_slot = self.IMAGE_EXACT_DUR if prefer == "image" else 7.0
                offset   = max(0.0, min(
                    (n_have + 1) * (sc_dur / (max_here + 1)),
                    sc_dur - dur_slot - 0.5,
                ))
                ok = self._inject_media(
                    sc, media_dir, used_urls,
                    offset=offset, clip_dur=dur_slot,
                    label=f"repair_cov{sc.get('scene_id','x')}_{n_have}",
                    prefer_type=prefer,
                    analysis=sc.get("_analysis"),
                )
                if ok:
                    violations_fixed["coverage"] += 1
                    consecutive_fails = 0
                    placed = True
                    break

            if not placed:
                consecutive_fails += 1

        # ── Report ────────────────────────────────────────────────────────────
        final_cov = self._compute_coverage(plan) / max(duration, 1) * 100
        tl_final  = _rebuild_tl()
        all_gaps  = []
        prev = 0.0
        for s, e in tl_final:
            if s - prev > self.MAX_GAP:
                all_gaps.append(s - prev)
            prev = max(prev, e)
        if duration - prev > self.MAX_GAP:
            all_gaps.append(duration - prev)

        print(f"   [L4] Repair complete:  coverage={final_cov:.0f}%  "
              f"clips_in_timeline={len(tl_final)}  "
              f"remaining_gaps>{self.MAX_GAP:.0f}s={len(all_gaps)}")
        print(f"   [L4] Fixed: opening={violations_fixed['opening']}  "
              f"gaps={violations_fixed['gap']}  "
              f"coverage_inserts={violations_fixed['coverage']}")
        return plan

    # =========================================================================
    # CANDIDATE RANKER — 11-category weighted scoring
    # =========================================================================

    def _rank_candidates(
        self,
        candidates: List[Dict],
        scene: Dict,
        analysis: Dict,
        wanted_type: str,
    ) -> List[Dict]:
        """
        Score every candidate on 11 dimensions. Weighted sum → final_score.
        Mutates candidates in place (adds 'final_score' + 'score_detail').
        Returns candidates sorted best-first.

        Categories:
          1.  entity_match      — candidate came from an entity-specific query
          2.  exact_match       — brand_query or query[0] hit (wave0)
          3.  scene_fit         — type matches the decision (video vs image)
          4.  resolution        — 1080p+ preferred
          5.  aspect_ratio      — 16:9 landscape preferred
          6.  source_priority   — reliable stock APIs rank higher
          7.  semantic_match    — base search score (query relevance via rank bonus)
          8.  duration_fit      — for videos: source duration fits slot
          9.  cinematic         — stock APIs that provide cinematic quality
          10. uniqueness        — penalize if URL domain already used in plan
          11. quality           — min-size pass (approximate quality signal)
        """
        want_video  = (wanted_type == "video")
        imp_score   = analysis.get("importance_score", 50)
        entity_spec = analysis.get("entity_specificity", 0)
        weights     = self._RANK_W

        for c in candidates:
            w = c.get("width",  0)
            h = c.get("height", 0)
            src = c.get("source", "")
            ctype = c.get("type", "image")
            base_score = float(c.get("score", 0))

            # 1. entity_match: was this result from a wave0 entity query?
            entity_match = float(c.get("_entity_bonus", 0))
            if entity_spec >= 40 and src in ("brave", "serper", "google"):
                entity_match = max(entity_match, 20.0)

            # 2. exact_match: base score already contains query-rank bonus
            exact_match = min(30.0, max(0.0, base_score - 50.0))

            # 3. scene_fit: does type match what we want?
            scene_fit = 20.0 if (ctype == wanted_type) else (5.0 if ctype == "image" else 0.0)

            # 4. resolution: reward 1080p+
            resolution = min(20.0, (w / 1920) * 20) if w > 0 else 8.0

            # 5. aspect_ratio: 16:9 landscape ideal
            ratio = w / h if (w > 0 and h > 0) else 0.0
            if ratio < 1.0:
                aspect_ratio = 0.0   # portrait — bad
            elif 1.6 <= ratio <= 2.0:
                aspect_ratio = 15.0  # 16:9 ideal
            elif 1.3 <= ratio < 1.6:
                aspect_ratio = 10.0  # 4:3 / slight landscape
            elif ratio > 2.0:
                aspect_ratio = 6.0   # ultra-wide
            else:
                aspect_ratio = 4.0

            # 6. source_priority: reliable download sources rank higher
            source_priority = float(self._SOURCE_PRIORITY.get(src, 3)) * 1.5

            # 7. semantic_match: normalized base score
            semantic_match = min(15.0, base_score * 0.15)

            # 8. duration_fit: for videos from pexels/pixabay, duration info not available
            # → give modest bonus for video sources when video is wanted
            duration_fit = 8.0 if (ctype == "video" and want_video) else 0.0

            # 9. cinematic: stock APIs with professional content
            cinematic = 10.0 if src in ("pexels", "pixabay", "coverr", "videvo") else 3.0

            # 10. uniqueness: penalize if same domain appears many times already
            uniqueness = 10.0  # default — TODO: track domain frequency if needed

            # 11. quality: file size proxy not available at search time → use resolution
            quality = min(10.0, resolution * 0.5)

            final_score = (
                entity_match    * weights["entity_match"]   +
                exact_match     * weights["exact_match"]    +
                scene_fit       * weights["scene_fit"]      +
                resolution      * weights["resolution"]     +
                aspect_ratio    * weights["aspect_ratio"]   +
                source_priority * weights["source_priority"]+
                semantic_match  * weights["semantic_match"] +
                duration_fit    * weights["duration_fit"]   +
                cinematic       * weights["cinematic"]      +
                uniqueness      * weights["uniqueness"]     +
                quality         * weights["quality"]
            )

            # Importance bonus: high-importance scenes get best-quality media
            if imp_score >= 75:
                final_score *= 1.1

            c["final_score"]  = round(final_score, 2)
            c["score_detail"] = {
                "entity_match": round(entity_match, 1),
                "exact_match":  round(exact_match,  1),
                "scene_fit":    round(scene_fit,     1),
                "resolution":   round(resolution,    1),
                "aspect_ratio": round(aspect_ratio,  1),
                "source":       src,
                "source_pri":   round(source_priority, 1),
                "cinematic":    round(cinematic, 1),
            }

        candidates.sort(key=lambda c: c.get("final_score", 0), reverse=True)
        return candidates

    # =========================================================================
    # PARALLEL WAVE SEARCH
    # =========================================================================

    def _parallel_search(self, query_waves: List[List[str]], media_type: str) -> List[Dict]:
        """
        Wave-based parallel search.  Wave 0 → 1 → 2.

        Wave 0 (entity queries):
          Brave + Serper run FIRST synchronously (real-world brand/entity images).
          Results get +20 entity_bonus flag for the CandidateRanker.
          Then all stock providers run in parallel for the same queries.

        Wave 1+ (visual queries):
          All providers run fully in parallel.
          Early stop when 6+ candidates score above GOOD_SCORE_THRESH.
        """
        want_video = (media_type == "video")
        k = self.keys

        # Provider definitions — lambdas capture k by reference
        stock_video_providers = [
            ("pexels_v",  lambda q: self._search_pexels(q, "video")  if k["pexels"]  else []),
            ("pixabay_v", lambda q: self._search_pixabay(q, "video") if k["pixabay"] else []),
            ("coverr",    lambda q: self._search_coverr(q)           if k["coverr"]  else []),
            ("videvo",    lambda q: self._search_videvo(q)           if k["videvo"]  else []),
        ]
        stock_image_providers = [
            ("pexels_i",  lambda q: self._search_pexels(q, "image")  if k["pexels"]   else []),
            ("pixabay_i", lambda q: self._search_pixabay(q, "image") if k["pixabay"]  else []),
            ("unsplash",  lambda q: self._search_unsplash(q)         if k["unsplash"] else []),
            ("google",    lambda q: self._search_google_images(q)    if k["gcs_key"]  else []),
        ]
        web_providers = [
            ("brave",  lambda q: self._search_brave_images(q)  if k["brave_search"] else []),
            ("serper", lambda q: self._search_serper_images(q) if k["serper"]       else []),
        ]

        # Build provider list for this search
        stock_providers = stock_video_providers if want_video else stock_image_providers
        all_providers   = stock_providers + web_providers
        if want_video:
            # Include image providers as last-resort fallback for video searches
            all_providers += stock_image_providers

        all_candidates: List[Dict] = []
        seen_urls: set = set()

        def _add(items: List[Dict], bonus: int, entity_bonus: float = 0.0):
            for item in (items or []):
                u = item.get("url", "")
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    item["score"] = item.get("score", 0) + bonus
                    if entity_bonus > 0:
                        item["_entity_bonus"] = item.get("_entity_bonus", 0) + entity_bonus
                    all_candidates.append(item)

        for wave_idx, queries in enumerate(query_waves):
            if not queries:
                continue

            is_entity_wave = (wave_idx == 0)

            # ── Entity wave: web search providers FIRST (synchronous) ─────────
            # Brave and Serper have real-world brand/entity images unavailable
            # in stock libraries. Run them first so entity hits flow into the pool.
            if is_entity_wave:
                for q_idx, q in enumerate(queries[:3]):
                    bonus = self._QUERY_BONUS[min(q_idx, len(self._QUERY_BONUS) - 1)]
                    if k["brave_search"]:
                        _add(self._search_brave_images(q), bonus, entity_bonus=20.0)
                    if k["serper"]:
                        _add(self._search_serper_images(q), bonus, entity_bonus=15.0)

            # ── All providers in parallel ──────────────────────────────────────
            max_workers = min(len(queries) * len(all_providers) + 1, 24)
            with ThreadPoolExecutor(max_workers=max_workers) as exe:
                futs: Dict[Future, Tuple[int, bool]] = {}
                for q_idx, q in enumerate(queries[:4]):
                    bonus = self._QUERY_BONUS[min(q_idx, len(self._QUERY_BONUS) - 1)]
                    for name, fn in all_providers:
                        # Skip web providers in wave0 — already ran above
                        if is_entity_wave and name in ("brave", "serper"):
                            continue
                        fut = exe.submit(fn, q)
                        futs[fut] = (bonus, is_entity_wave and q_idx == 0)

                for fut in as_completed(futs, timeout=self.SEARCH_TIMEOUT * 5):
                    bonus, is_top_q = futs[fut]
                    ent_bonus = 8.0 if is_top_q else 0.0
                    try:
                        _add(fut.result(timeout=0), bonus, ent_bonus)
                    except Exception:
                        pass

            # Early stop: 6+ strong candidates → enough to pick from
            good = sum(1 for c in all_candidates
                       if c.get("score", 0) >= self.GOOD_SCORE_THRESH)
            if good >= 6:
                break

        return all_candidates

    def _download_parallel(
        self,
        candidates: List[Dict],
        media_dir: Path,
        scene_id,
    ) -> Optional[Dict]:
        """
        Parallel download engine: try the top N candidates simultaneously,
        return the first one that succeeds. Much faster than sequential retries
        when Brave/Serper URLs have hotlink protection (would otherwise block 3-10s each).

        Strategy:
          - First try session/disk cache (instant, no network)
          - Launch parallel downloads of top 4 candidates
          - Return first success; ignore the rest
          - Fall back to sequential for remaining candidates if parallel phase fails
        """
        if not candidates:
            return None

        # Sort by final_score (set by _rank_candidates), fall back to base score
        sorted_cands = sorted(candidates,
                              key=lambda c: c.get("final_score", c.get("score", 0)),
                              reverse=True)

        # ── Phase 1: Cache check (no network) ────────────────────────────────
        for c in sorted_cands[:14]:
            url = c.get("url", "")
            if not url:
                continue
            # Session cache
            if url in self._url_cache:
                cached = self._url_cache[url]
                if Path(cached).exists():
                    c["local_path"] = cached
                    return c
            # Disk cache
            is_v = c.get("type") == "video"
            uid  = hashlib.md5(url.encode()).hexdigest()[:10]
            lp   = media_dir / f"s{scene_id}_{uid}{'.mp4' if is_v else '.jpg'}"
            if lp.exists() and lp.stat().st_size > (100_000 if is_v else 15_000):
                if self._is_valid_media(lp):
                    c["local_path"] = str(lp)
                    self._url_cache[url] = str(lp)
                    return c

        # ── Phase 2: Parallel downloads of top 4 ─────────────────────────────
        # Uses an event to let the first successful thread signal others to stop early
        success_holder: List[Optional[Dict]] = [None]
        success_event  = threading.Event()
        dl_lock        = threading.Lock()

        def _try_one(c: Dict) -> Optional[Dict]:
            if success_event.is_set():
                return None   # another thread already succeeded
            url = c.get("url", "")
            if not url:
                return None
            is_v = c.get("type") == "video"
            uid  = hashlib.md5(url.encode()).hexdigest()[:10]
            lp   = media_dir / f"s{scene_id}_{uid}{'.mp4' if is_v else '.jpg'}"
            ok   = self._download(url, lp, timeout=20, retries=1)
            if not ok or success_event.is_set():
                return None
            detected = self._detect_media_type(lp)
            if detected == "unknown":
                lp.unlink(missing_ok=True)
                return None
            real_ext = ".mp4" if detected == "video" else self._real_img_ext(lp)
            if lp.suffix.lower() != real_ext:
                np_ = lp.with_suffix(real_ext)
                lp.rename(np_)
                lp = np_
            c["type"]       = detected
            c["local_path"] = str(lp)
            self._url_cache[url] = str(lp)
            return c

        # Launch top-4 in parallel
        par_pool = sorted_cands[:4]
        with ThreadPoolExecutor(max_workers=4) as exe:
            futs = {exe.submit(_try_one, c): c for c in par_pool}
            for fut in as_completed(futs, timeout=25):
                try:
                    res = fut.result()
                    if res:
                        with dl_lock:
                            if success_holder[0] is None:
                                success_holder[0] = res
                                success_event.set()
                                src = res.get("source", "?")
                                fs  = res.get("final_score", res.get("score", 0))
                                print(f"   ✔ {scene_id} — {src} {res.get('type','?')}"
                                      f"  final={fs:.0f}  parallel-win")
                except Exception:
                    pass

        if success_holder[0]:
            return success_holder[0]

        # ── Phase 3: Sequential fallback for remaining candidates ─────────────
        return self._download_best(sorted_cands[4:10], media_dir, scene_id)

    def _download_best(
        self,
        candidates: List[Dict],
        media_dir: Path,
        scene_id: int,
    ) -> Optional[Dict]:
        """
        Download best candidate.  Strategy:
          1. Check session cache (instant hit)
          2. Check disk cache (previous run)
          3. Download in order (best final_score first, up to 14 tries)
          4. After download: magic-bytes detect type, rename to real ext, validate

        Brave/Serper URLs often fail hotlink protection so we need a deep pool.
        Stock API URLs (Pexels, Pixabay) are ranked higher by CandidateRanker.
        """
        # Use final_score if available (set by _rank_candidates), else score
        candidates_sorted = sorted(
            candidates,
            key=lambda c: c.get("final_score", c.get("score", 0)),
            reverse=True,
        )

        tried = 0
        for candidate in candidates_sorted[:14]:
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
            fs = candidate.get("final_score", candidate.get("score", 0))
            det = candidate.get("score_detail", {})
            print(f"   ✔ scene {scene_id} — {src_label} {detected}"
                  f"  final={fs:.0f}  {candidate.get('width',0)}×{candidate.get('height',0)}"
                  f"  entity={det.get('entity_match',0):.0f}"
                  f"  type_fit={det.get('scene_fit',0):.0f}")
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
        """Detect media type — magic bytes FIRST (prevents MJPEG/JPEG misdetection)."""
        # Magic bytes FIRST — JPEG/PNG/WEBP/GIF/BMP identified instantly and correctly.
        # ffprobe stream=codec_type returns "video" for JPEG (MJPEG codec), so we must
        # check image signatures before ever calling ffprobe.
        try:
            with open(path, "rb") as f:
                header = f.read(12)
            if (header[:3] == b"\xff\xd8\xff"              # JPEG
                    or header[:8] == b"\x89PNG\r\n\x1a\n"  # PNG
                    or b"WEBP" in header                    # WEBP
                    or header[:6] in (b"GIF87a", b"GIF89a") # GIF
                    or header[:2] == b"BM"):                # BMP
                return "image"
        except Exception:
            pass
        # Use ffprobe format_name (not codec_type) to detect real video containers.
        # format_name is container-based and never misidentifies JPEG as video.
        try:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=format_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                          timeout=10).decode().strip().lower()
            video_formats = ("mp4", "matroska", "webm", "avi", "mov",
                             "flv", "mkv", "wmv", "m4v", "3gp")
            if any(vf in out for vf in video_formats):
                return "video"
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

        # 8 workers (up from 4). FFmpeg uses -threads 0 per process so each
        # already uses multiple CPU cores, but 8 concurrent processes still helps
        # on modern multi-core machines for I/O-bound jobs.
        with ThreadPoolExecutor(max_workers=8) as exe:
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
            # Still image → clip.
            # CRF 40 + tune stillimage = ultrafast, tiny file, still looks fine
            # as a 3-second overlay.  2 fps is enough for a static image.
            ok = _run_ffmpeg([
                "-loop", "1",
                "-framerate", "2",
                "-i", src,
                "-vf", scale_filter,
                "-t", str(round(duration, 3)),
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
                "-crf", "40",
                "-tune", "stillimage",
                "-g", "600",
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

            # FAST PATH: try stream copy first (instantaneous when source is already H.264)
            # Only works for mp4/mov containers; will fail gracefully otherwise.
            ok = _run_ffmpeg([
                "-ss", "0",
                "-i", src,
                "-t", str(round(trim, 3)),
                "-vf", scale_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
                "-crf", "32",   # raised from 26 — temp files don't need high quality
                "-pix_fmt", "yuv420p", "-an",
                "-movflags", "+faststart",
                dst,
            ], label="vid→clip")

            if not ok:
                # Fallback: -vsync vfr for unusual frame-rate sources
                ok = _run_ffmpeg([
                    "-i", src,
                    "-t", str(round(trim, 3)),
                    "-vf", scale_filter,
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "0",
                    "-crf", "32",
                    "-pix_fmt", "yuv420p", "-vsync", "vfr", "-an",
                    "-movflags", "+faststart",
                    dst,
                ], label="vid→clip-vfr")
            return ok

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 4 — RENDER
    # ─────────────────────────────────────────────────────────────────────────

    # ── Shared FFmpeg output quality params ───────────────────────────────────
    # CRF 26 = high quality, 32 = good quality (30% faster encode).
    # For a 20-min 1080p video, CRF 26 → ~15 min render; CRF 32 → ~10 min.
    _RENDER_CRF     = "26"
    _RENDER_PRESET  = "ultrafast"
    # Max clips in a single filter_complex pass (above this we batch)
    _MAX_FC_CLIPS   = 50

    def _build_overlay_cmd(
        self, avatar_path: str, timeline: List[Dict], out_path: str
    ) -> List[str]:
        """Build a single-pass FFmpeg overlay command for a given timeline."""
        inputs = ["-i", avatar_path]
        for item in timeline:
            inputs += ["-i", item["clip_path"]]

        scale_base = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1[base]"
        )
        parts = [scale_base]
        prev  = "base"
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

        return (
            inputs
            + ["-filter_complex", ";".join(parts)]
            + ["-map", f"[{prev}]", "-map", "0:a?"]
            + ["-c:v", "libx264",
               "-preset", self._RENDER_PRESET,
               "-threads", "0",
               "-crf", self._RENDER_CRF]
            + ["-c:a", "aac", "-b:a", "192k"]
            + ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            + [out_path]
        )

    def _render(self, avatar_path: str, timeline: List[Dict], out_path: str):
        """
        Render final video: avatar base track + B-roll overlays.

        For small timelines (≤ MAX_FC_CLIPS): single FFmpeg filter_complex pass.
        For large timelines (> MAX_FC_CLIPS): batch into groups of MAX_FC_CLIPS,
          render each batch to a temp intermediate, then fast-concat all
          intermediates.  This avoids FFmpeg memory/node-limit issues and is
          faster because each sub-render is smaller.

        Fallback chain:
          1. Full overlay pass
          2. Drop last 30% of clips and retry
          3. Avatar-only (with detailed diagnostic log)
        """
        if not timeline:
            print("   ⚠️  No B-roll timeline — all downloads/preprocessing failed.")
            print("   ⚠️  Possible causes: all API keys missing, hotlink blocks, ffprobe errors.")
            self._progress(80, "No B-roll clips — avatar-only output. Check API keys.")
            self._render_avatar_only(avatar_path, out_path)
            return

        # Safety filter: only include clips that exist and are non-empty
        valid = []
        for t in timeline:
            p = Path(t["clip_path"])
            if p.exists() and p.stat().st_size > 500:
                valid.append(t)
            else:
                print(f"   ⚠️  Missing/empty clip skipped: {p.name}")
        timeline = valid

        if not timeline:
            print("   ⚠️  All preprocessed clips are missing or empty on disk.")
            print("   ⚠️  FFmpeg preprocessing likely failed — see errors above.")
            self._progress(80, "No valid clips after preprocessing — avatar-only output")
            self._render_avatar_only(avatar_path, out_path)
            return

        n = len(timeline)
        print(f"   📹 Rendering {n} B-roll clips into final video…")
        for i, t in enumerate(timeline[:8]):
            dur = t["end"] - t["start"]
            print(f"      [{i+1}] t={t['start']:.1f}s  dur={dur:.1f}s  "
                  f"{t.get('type','?')}  {t.get('source','?')}  "
                  f"{Path(t['clip_path']).name}")
        if n > 8:
            print(f"      … and {n-8} more clips")

        self._progress(76, f"FFmpeg overlay render — {n} clips…")

        # ── Single-pass render (fast path) ────────────────────────────────────
        if n <= self._MAX_FC_CLIPS:
            cmd = self._build_overlay_cmd(avatar_path, timeline, out_path)
            ok  = _run_ffmpeg(cmd, label=f"overlay-{n}clips")
            if ok:
                return
            # First retry: drop last 30%
            print(f"   ⚠️  Overlay render failed — retrying with 70% of clips…")
            reduced = timeline[:max(1, int(n * 0.7))]
            ok2 = _run_ffmpeg(
                self._build_overlay_cmd(avatar_path, reduced, out_path),
                label=f"overlay-{len(reduced)}clips-retry",
            )
            if ok2:
                print(f"   ✔ Render succeeded with {len(reduced)} clips")
                return
            # Final fallback
            print("   ⚠️  All overlay attempts failed — avatar-only fallback.")
            self._progress(90, "Render failed — avatar-only output")
            self._render_avatar_only(avatar_path, out_path)
            return

        # ── Batched render for large timelines ────────────────────────────────
        # Split into batches of MAX_FC_CLIPS, render each to temp file,
        # then concat all temp files (avatar audio preserved from batch 0).
        self._progress(77, f"Large timeline ({n} clips) — batched render…")
        batch_size = self._MAX_FC_CLIPS
        batches    = [timeline[i:i+batch_size]
                      for i in range(0, n, batch_size)]
        batch_files: List[str] = []
        tmp_dir = Path(out_path).parent / "render_tmp"
        tmp_dir.mkdir(exist_ok=True)

        for bi, batch in enumerate(batches):
            tmp_out = str(tmp_dir / f"batch_{bi}.mp4")
            self._progress(77 + int(bi / len(batches) * 8),
                           f"Rendering batch {bi+1}/{len(batches)} ({len(batch)} clips)…")
            cmd = self._build_overlay_cmd(avatar_path, batch, tmp_out)
            ok  = _run_ffmpeg(cmd, label=f"batch-{bi}")
            if not ok:
                print(f"   ⚠️  Batch {bi+1} failed — using avatar track for this segment")
                # Fallback: encode just avatar for this segment's time range
                seg_start = batch[0]["start"]
                seg_end   = batch[-1]["end"]
                ok = _run_ffmpeg([
                    "-ss", str(seg_start), "-i", avatar_path,
                    "-t", str(seg_end - seg_start),
                    "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", self._RENDER_CRF, "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    tmp_out,
                ], label=f"batch-{bi}-fallback")
            if ok:
                batch_files.append(tmp_out)

        if not batch_files:
            print("   ⚠️  All batches failed — avatar-only fallback")
            self._render_avatar_only(avatar_path, out_path)
            return

        if len(batch_files) == 1:
            import shutil
            shutil.move(batch_files[0], out_path)
            return

        # Concat all batch files
        self._progress(87, f"Concatenating {len(batch_files)} batch segments…")
        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{f}'" for f in batch_files))
        ok = _run_ffmpeg([
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            out_path,
        ], label="concat-batches")
        if not ok:
            # If concat fails, just use the first batch
            import shutil
            shutil.copy(batch_files[0], out_path)

    def _render_with_timeline(self, avatar_path: str, timeline: List[Dict],
                               out_path: str) -> bool:
        """Re-render with a given timeline. Returns True on success."""
        if not timeline:
            return False
        cmd = self._build_overlay_cmd(avatar_path, timeline, out_path)
        return _run_ffmpeg(cmd, label="overlay-render-retry")

    def _render_avatar_only(self, avatar_path: str, out_path: str):
        """Encode avatar to 1080p H.264 with no overlays."""
        _run_ffmpeg([
            "-i", avatar_path,
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1",
            "-c:v", "libx264",
            "-preset", self._RENDER_PRESET,
            "-threads", "0",
            "-crf", self._RENDER_CRF,
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            out_path,
        ], label="avatar-only")



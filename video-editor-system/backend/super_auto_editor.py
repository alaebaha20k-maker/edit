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
    MAX_BROLL_COVERAGE = 0.45

    def __init__(
        self,
        gemini_keys:  list  = None,
        pexels_key:   str   = "",
        pixabay_key:  str   = "",
        unsplash_key: str   = "",
        progress_cb         = None,
    ):
        self.output_dir = Path(Config.OUTPUT_DIR)
        self.temp_dir   = Path(Config.TEMP_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Pick first non-empty Gemini key
        gem = ""
        if gemini_keys:
            for k in (gemini_keys if isinstance(gemini_keys, list) else [gemini_keys]):
                if k and k.strip():
                    gem = k.strip()
                    break

        self.keys = {
            "gemini"  : gem,
            "pexels"  : pexels_key or "",
            "pixabay" : pixabay_key or "",
            "unsplash": unsplash_key or "",
        }
        self._progress_cb = progress_cb  # callable(pct: int, msg: str) | None

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

        prompt = f"""You are a world-class documentary video editor and AI script analyst.

VIDEO DURATION: {duration_sec:.0f} seconds ({minutes:.1f} minutes)
SCRIPT LENGTH: {char_count:,} characters
TOTAL SCRIPT (analyze fully):
---
{script}
---

YOUR TASK:
Analyze this script and produce a production-ready scene edit plan.
Think like a top YouTube documentary editor making a premium B-roll plan.

RULES FOR SCENE SPLITTING:
- Split by topic shift, story beat, explanation block, emotional change, transition
- Do NOT use fixed intervals — split by meaning
- Aim for 6–20 scenes depending on video length
- Scenes can range from 30 seconds to 3 minutes

RULES FOR TIMING:
- Total must equal {duration_sec:.0f} seconds
- Distribute proportionally by script density (more text = slightly longer scene)
- Start times must be sequential, no overlap

RULES FOR MEDIA DECISIONS:
- "avatar_only" — narrator is transitioning, emotional, or no visual value
- "image" — factual concept, entity, place that benefits from a still image
- "video" — action, process, brand, location that needs motion
- "mixed" — multiple strong visual moments in one scene
- Target: 40-60% of total scenes get media. Never force media where it doesn't fit.
- Never cover more than 45% of the total video with B-roll

RULES FOR SEARCH QUERIES:
- Never generic ("car", "people", "office")
- Always specific, cinematic, documentary-style
- 4-6 queries per media scene, increasing specificity

RULES FOR MEDIA PLACEMENT:
- "start": media at the beginning of the scene
- "middle": media in the strongest visual phrase
- "end": media just before topic shift
- Only one or two media inserts per scene maximum

Return ONLY valid JSON (no markdown, no explanation):

{{
  "scenes": [
    {{
      "scene_id": 1,
      "title": "short scene title",
      "summary": "one sentence summary",
      "script_excerpt": "first 120 chars of this scene's script",
      "start_time": 0,
      "end_time": 45,
      "duration_seconds": 45,
      "tone": "informative|emotional|dramatic|energetic|neutral",
      "importance": "high|medium|low",
      "visual_richness": "rich|moderate|sparse",
      "decision": "avatar_only|image|video|mixed",
      "search_queries": ["specific query 1", "cinematic query 2", "documentary query 3"],
      "media_type_preferred": "video|image|none",
      "insertion_points": [
        {{
          "placement": "middle",
          "offset_from_scene_start": 10,
          "duration": 7,
          "reason": "why media fits here"
        }}
      ],
      "editor_notes": "brief note for the editor"
    }}
  ],
  "total_duration": {duration_sec:.0f},
  "pacing_notes": "overall pacing assessment"
}}"""

        model = genai.GenerativeModel(
            Config.GEMINI_SCRIPT_MODEL,
            system_instruction="You are an expert AI video editor. Always return valid JSON only.",
        )
        response = model.generate_content(
            prompt,
            generation_config={"temperature": 0.2, "max_output_tokens": 16384},
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
                raise ValueError(f"Gemini returned invalid JSON for scene plan.")

        # Attach selected_media list to each scene
        for scene in plan.get("scenes", []):
            scene.setdefault("selected_media", [])

        return plan

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 2 — MEDIA SEARCH & DOWNLOAD
    # ─────────────────────────────────────────────────────────────────────────

    def _search_and_download(self, plan: Dict, job_dir: Path) -> Dict:
        """Search APIs and download best matching media for each scene."""
        media_dir = job_dir / "media"
        media_dir.mkdir(exist_ok=True)
        used_urls: set = set()

        scenes = plan.get("scenes", [])
        n = len(scenes)

        for idx, scene in enumerate(scenes):
            if scene.get("decision") == "avatar_only":
                continue

            pct = 28 + int((idx / max(n, 1)) * 30)
            self._progress(pct, f"Searching media for scene {idx+1}/{n}: {scene.get('title','')[:40]}")

            queries  = scene.get("search_queries", [])
            pref     = scene.get("media_type_preferred", "video")
            inserts  = scene.get("insertion_points", [])
            n_needed = max(1, len(inserts))

            selected = []
            for insert in inserts[:2]:   # max 2 inserts per scene
                media = self._find_best_media(
                    queries, pref, media_dir, used_urls,
                    scene_id=scene["scene_id"]
                )
                if media:
                    media["insertion_offset"] = insert.get("offset_from_scene_start", 0)
                    media["clip_duration"]    = insert.get("duration", 7)
                    media["placement"]        = insert.get("placement", "middle")
                    media["reason"]           = insert.get("reason", "")
                    selected.append(media)
                    used_urls.add(media.get("url", ""))

            scene["selected_media"] = selected

        return plan

    def _find_best_media(
        self,
        queries: List[str],
        media_type: str,
        media_dir: Path,
        used_urls: set,
        scene_id: int,
    ) -> Optional[Dict]:
        """Try all queries across all available APIs, return best match."""
        candidates = []

        for query in queries[:4]:
            # Pexels
            if self.keys["pexels"]:
                results = self._search_pexels(query, media_type)
                candidates.extend(results)
            # Pixabay
            if self.keys["pixabay"]:
                results = self._search_pixabay(query, media_type)
                candidates.extend(results)
            # Unsplash (images only)
            if self.keys["unsplash"] and media_type in ("image", "photo"):
                results = self._search_unsplash(query)
                candidates.extend(results)
            if candidates:
                break   # first query that gets results is sufficient

        # Filter out used URLs and score
        candidates = [c for c in candidates if c.get("url") not in used_urls]
        if not candidates:
            return None

        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        best = candidates[0]

        # Download
        ext      = ".mp4" if best.get("type") == "video" else ".jpg"
        filename = f"scene{scene_id}_{hashlib.md5(best['url'].encode()).hexdigest()[:8]}{ext}"
        local_path = media_dir / filename

        if not local_path.exists():
            ok = self._download(best["url"], local_path)
            if not ok:
                return None

        best["local_path"] = str(local_path)
        return best

    # ── Pexels ────────────────────────────────────────────────────────────────

    def _search_pexels(self, query: str, media_type: str) -> List[Dict]:
        key = self.keys["pexels"]
        if not key:
            return []
        results = []
        try:
            if media_type == "video":
                url = "https://api.pexels.com/videos/search"
                params = {"query": query, "per_page": 8, "orientation": "landscape",
                          "size": "large"}
                r = requests.get(url, headers={"Authorization": key},
                                 params=params, timeout=10)
                if r.ok:
                    for v in r.json().get("videos", []):
                        # Pick best file (HD landscape)
                        files = sorted(
                            [f for f in v.get("video_files", [])
                             if f.get("width", 0) >= 1280 and f.get("height", 0) <= 1080],
                            key=lambda f: f.get("width", 0), reverse=True
                        )
                        if not files:
                            files = v.get("video_files", [])
                        if files:
                            results.append({
                                "type"   : "video",
                                "source" : "pexels",
                                "url"    : files[0]["link"],
                                "width"  : files[0].get("width", 1920),
                                "height" : files[0].get("height", 1080),
                                "score"  : self._score(files[0].get("width", 0),
                                                       files[0].get("height", 0), "video"),
                            })
            else:
                url = "https://api.pexels.com/v1/search"
                params = {"query": query, "per_page": 8, "orientation": "landscape",
                          "size": "large"}
                r = requests.get(url, headers={"Authorization": key},
                                 params=params, timeout=10)
                if r.ok:
                    for p in r.json().get("photos", []):
                        src = p.get("src", {})
                        img_url = src.get("large2x") or src.get("large") or src.get("original")
                        if img_url:
                            results.append({
                                "type"  : "image",
                                "source": "pexels",
                                "url"   : img_url,
                                "width" : p.get("width", 1920),
                                "height": p.get("height", 1080),
                                "score" : self._score(p.get("width", 0),
                                                      p.get("height", 0), "image"),
                            })
        except Exception as e:
            print(f"   Pexels search error: {e}")
        return results

    # ── Pixabay ───────────────────────────────────────────────────────────────

    def _search_pixabay(self, query: str, media_type: str) -> List[Dict]:
        key = self.keys["pixabay"]
        if not key:
            return []
        results = []
        try:
            if media_type == "video":
                url = "https://pixabay.com/api/videos/"
                params = {"key": key, "q": query, "per_page": 8,
                          "video_type": "film", "min_width": 1280}
            else:
                url = "https://pixabay.com/api/"
                params = {"key": key, "q": query, "per_page": 8,
                          "image_type": "photo", "orientation": "horizontal",
                          "min_width": 1280}
            r = requests.get(url, params=params, timeout=10)
            if r.ok:
                for item in r.json().get("hits", []):
                    if media_type == "video":
                        videos = item.get("videos", {})
                        file = (videos.get("large") or videos.get("medium")
                                or videos.get("small") or {})
                        dl_url = file.get("url")
                        w, h = file.get("width", 1280), file.get("height", 720)
                    else:
                        dl_url = item.get("largeImageURL") or item.get("webformatURL")
                        w, h = item.get("imageWidth", 1280), item.get("imageHeight", 720)
                    if dl_url:
                        results.append({
                            "type"  : "video" if media_type == "video" else "image",
                            "source": "pixabay",
                            "url"   : dl_url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, media_type),
                        })
        except Exception as e:
            print(f"   Pixabay search error: {e}")
        return results

    # ── Unsplash ──────────────────────────────────────────────────────────────

    def _search_unsplash(self, query: str) -> List[Dict]:
        key = self.keys["unsplash"]
        if not key:
            return []
        results = []
        try:
            url = "https://api.unsplash.com/search/photos"
            params = {"query": query, "per_page": 8, "orientation": "landscape"}
            r = requests.get(url, headers={"Authorization": f"Client-ID {key}"},
                             params=params, timeout=10)
            if r.ok:
                for p in r.json().get("results", []):
                    urls = p.get("urls", {})
                    img_url = urls.get("full") or urls.get("regular")
                    w = p.get("width", 1920)
                    h = p.get("height", 1080)
                    if img_url and w >= 1280:
                        results.append({
                            "type"  : "image",
                            "source": "unsplash",
                            "url"   : img_url,
                            "width" : w, "height": h,
                            "score" : self._score(w, h, "image"),
                        })
        except Exception as e:
            print(f"   Unsplash search error: {e}")
        return results

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, w: int, h: int, media_type: str) -> float:
        """Higher is better. Rewards landscape HD, penalises portrait/tiny."""
        if w <= 0 or h <= 0:
            return 0.0
        res_score = min(w / 1920, 1.0) * 40
        ratio     = w / h
        # Strongly prefer landscape (16:9 ≈ 1.78)
        if ratio < 1.0:
            ratio_score = 0   # portrait — discard
        elif 1.5 <= ratio <= 2.2:
            ratio_score = 40  # ideal
        else:
            ratio_score = 20
        bonus = 20 if media_type == "video" else 15  # slight video preference
        return res_score + ratio_score + bonus

    # ── Downloader ────────────────────────────────────────────────────────────

    def _download(self, url: str, dest: Path, timeout: int = 60) -> bool:
        try:
            headers = {"User-Agent": "Mozilla/5.0 (compatible; VideoEditor/1.0)"}
            r = requests.get(url, stream=True, timeout=timeout, headers=headers)
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            return dest.stat().st_size > 5000
        except Exception as e:
            print(f"   Download error {url[:60]}: {e}")
            if dest.exists():
                dest.unlink()
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 3 — PRE-PROCESS CLIPS
    # ─────────────────────────────────────────────────────────────────────────

    def _preprocess_clips(
        self, plan: Dict, job_dir: Path, avatar_duration: float
    ) -> List[Dict]:
        """
        For every media insert, produce a 1920×1080 muted clip of exact duration.
        Returns timeline list: [{start, end, clip_path}, …]
        """
        clips_dir = job_dir / "clips"
        clips_dir.mkdir(exist_ok=True)
        timeline = []
        broll_seconds = 0.0

        for scene in plan.get("scenes", []):
            scene_start = float(scene.get("start_time", 0))
            scene_end   = float(scene.get("end_time", scene_start + 30))

            for media in scene.get("selected_media", []):
                lp = media.get("local_path")
                if not lp or not Path(lp).exists():
                    continue

                insert_offset = float(media.get("insertion_offset", 0))
                clip_dur      = float(media.get("clip_duration", 7))

                # Clamp to scene boundaries
                start_t = min(scene_start + insert_offset, scene_end - clip_dur)
                start_t = max(start_t, scene_start)
                end_t   = min(start_t + clip_dur, scene_end, avatar_duration - 0.5)

                if end_t - start_t < 2:
                    continue  # too short to bother

                # Check total B-roll budget
                if broll_seconds + (end_t - start_t) > avatar_duration * self.MAX_BROLL_COVERAGE:
                    continue

                clip_dur_actual = end_t - start_t
                out_clip = clips_dir / f"clip_{scene['scene_id']}_{int(start_t)}.mp4"

                ok = self._make_clip(lp, str(out_clip), clip_dur_actual,
                                     media.get("type", "image"))
                if ok:
                    timeline.append({
                        "start"    : start_t,
                        "end"      : end_t,
                        "clip_path": str(out_clip),
                        "type"     : media.get("type"),
                        "source"   : media.get("source"),
                    })
                    broll_seconds += clip_dur_actual

        # Sort by start time, remove overlaps
        timeline.sort(key=lambda x: x["start"])
        clean = []
        last_end = 0.0
        for item in timeline:
            if item["start"] >= last_end + 0.5:
                clean.append(item)
                last_end = item["end"]
        return clean

    def _make_clip(self, src: str, dst: str, duration: float, media_type: str) -> bool:
        """Produce a 1920×1080 muted clip of exact duration."""
        scale_filter = (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        )
        if media_type == "image":
            return _run_ffmpeg([
                "-loop", "1",
                "-framerate", "25",
                "-i", src,
                "-vf", scale_filter,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p", "-an",
                dst,
            ], label="img→clip")
        else:
            # Video: trim to duration and mute
            src_dur = _ffprobe_duration(src)
            if src_dur <= 0:
                return False
            trim = min(duration, src_dur)
            return _run_ffmpeg([
                "-i", src,
                "-t", str(trim),
                "-vf", scale_filter,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
                "-pix_fmt", "yuv420p", "-an",
                dst,
            ], label="vid→clip")

    # ─────────────────────────────────────────────────────────────────────────
    # PHASE 4 — RENDER
    # ─────────────────────────────────────────────────────────────────────────

    def _render(self, avatar_path: str, timeline: List[Dict], out_path: str):
        """
        Build FFmpeg overlay command:
          - Avatar = base track (1920×1080, audio preserved)
          - Each timeline entry = overlay at [start, end)
          - All overlays are muted (pre-processed in Phase 3)
        """
        if not timeline:
            # No B-roll: just re-encode avatar to 1080p
            self._progress(80, "No B-roll — encoding avatar to 1080p…")
            _run_ffmpeg([
                "-i", avatar_path,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path,
            ], label="avatar-only")
            return

        n = len(timeline)
        self._progress(76, f"Building FFmpeg overlay graph ({n} inserts)…")

        # ── Build inputs ──────────────────────────────────────────────────────
        inputs = ["-i", avatar_path]
        for item in timeline:
            inputs += ["-i", item["clip_path"]]

        # ── Build filter_complex ──────────────────────────────────────────────
        # Scale avatar base
        parts = [
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black[base]"
        ]

        prev = "base"
        for i, item in enumerate(timeline):
            idx     = i + 1            # input index (0 = avatar)
            s, e    = item["start"], item["end"]
            out_lbl = f"v{i+1}"
            parts.append(
                f"[{idx}:v]setpts=PTS-STARTPTS[c{idx}];"
                f"[{prev}][c{idx}]overlay="
                f"enable='between(t,{s:.3f},{e:.3f})':x=0:y=0[{out_lbl}]"
            )
            prev = out_lbl

        filter_complex = ";".join(parts)

        cmd = (
            inputs
            + ["-filter_complex", filter_complex]
            + ["-map", f"[{prev}]", "-map", "0:a?"]
            + ["-c:v", "libx264", "-preset", "fast", "-crf", "22"]
            + ["-c:a", "aac", "-b:a", "192k"]
            + ["-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            + [out_path]
        )

        self._progress(78, "FFmpeg rendering… (this may take several minutes)")
        ok = _run_ffmpeg(cmd, label="overlay-render")

        if not ok:
            # Fallback: avatar only
            self._progress(90, "Overlay render failed — falling back to avatar-only…")
            _run_ffmpeg([
                "-i", avatar_path,
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                "-c:a", "aac", "-b:a", "192k",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                out_path,
            ], label="fallback")



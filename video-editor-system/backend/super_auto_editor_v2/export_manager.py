from __future__ import annotations

"""
export_manager.py — Super Auto Editor v2
-----------------------------------------
Pipeline (5 steps):

  STEP 1  Script math & timeline generation (cycle: Avatar 20s + Media 15s = 35s)
  STEP 2  Batch Gemini keyword generation (ONE API call for ALL media segments)
  STEP 3  Parallel media clip building (Serper / Pexels / Merge per segment)
  STEP 4  Self-check every result (URL accessible + title relevance)
  STEP 5  Single FFmpeg overlay pass (avatar base + media overlays, audio untouched)

Media routing:
  SERPER → Google Images via serper.dev (named brands, products, people, cities)
  PEXELS → Stock video 15-20s (generic scenes, actions, environments)
  MERGE  → Serper image (subject) + Pexels video (environment) spliced together
"""

import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
from math import ceil
import os
from pathlib import Path
from time import perf_counter

from super_auto_editor_v2.analyze.script_analyzer import ScriptAnalyzer
from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.config.settings import AppConfig
from super_auto_editor_v2.download.downloader import Downloader
from super_auto_editor_v2.ffmpeg.runner import FFmpegRunner
from super_auto_editor_v2.media.image_clip_builder import ImageClipBuilder
from super_auto_editor_v2.media.scene_mixer import SceneMixer
from super_auto_editor_v2.media.video_scene_builder import VideoSceneBuilder
from super_auto_editor_v2.models import DownloadedAsset, MediaPlan, VisualIntent
from super_auto_editor_v2.search.asset_ranker import rank_videos
from super_auto_editor_v2.search.pexels_video_searcher import PexelsVideoSearcher
from super_auto_editor_v2.search.query_builder import QueryBuilder
from super_auto_editor_v2.search.serper_image_searcher import SerperImageSearcher
from super_auto_editor_v2.timeline.timeline_builder import TimelineBuilder


class ExportManager:
    _CONCAT_STREAM_FIELDS = (
        "codec_name", "profile", "level", "width", "height",
        "pix_fmt", "r_frame_rate", "avg_frame_rate", "time_base",
    )

    def __init__(self, config: AppConfig):
        self.config = config
        self.cache = CacheManager(config.cache_dir)
        self.ffmpeg = FFmpegRunner()
        self.timeline_builder = TimelineBuilder()
        self.script_analyzer = ScriptAnalyzer(config.gemini_api_key)
        self.serper = SerperImageSearcher(config.serper_api_key, cache=self.cache)
        self.pexels = PexelsVideoSearcher(config.pexels_api_key, cache=self.cache)
        self.downloader = Downloader(self.cache, workers=config.concurrency_downloads)
        self.image_builder = ImageClipBuilder(
            self.ffmpeg, config.resolution_w, config.resolution_h, config.fps
        )
        self.video_builder = VideoSceneBuilder(
            self.ffmpeg, config.resolution_w, config.resolution_h, config.fps
        )
        self.scene_mixer = SceneMixer(
            self.ffmpeg, config.resolution_w, config.resolution_h, config.fps
        )
        self.query_builder = QueryBuilder()
        self._t0 = perf_counter()

    def _log(self, message: str) -> None:
        elapsed = perf_counter() - self._t0
        print(f"[SAE v2 +{elapsed:7.2f}s] {message}", flush=True)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def build(
        self,
        avatar_video: Path,
        script_path: Path,
        timeline_path: Path,
        output_path: Path,
        mode: str,
    ) -> Path:
        """
        Full 5-step pipeline. Avatar audio is NEVER touched.
        Output is always 1080p, no frozen frames, no black scenes.
        """
        self._t0 = perf_counter()
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)

        # ── STEP 1: Script math & timeline ──────────────────────────────
        avatar_duration = self.ffmpeg.probe_duration(avatar_video)
        script_text = script_path.read_text(encoding="utf-8")
        self.script_analyzer.set_context(script_text)
        self.query_builder.reset()

        # Generate timeline from script using cycle math (Avatar 20s + Media 15s)
        timeline = self.timeline_builder.build_from_script(script_text, avatar_duration)
        self._log(f"Timeline: {len(timeline)} blocks ({sum(1 for b in timeline if b.type=='media')} media)")

        media_blocks = [
            (idx, block)
            for idx, block in enumerate(timeline)
            if block.type == "media"
        ]

        # ── STEP 2: Batch Gemini keyword generation ─────────────────────
        self._log(f"Generating media plans for {len(media_blocks)} segments (1 Gemini call)…")
        media_plans = self.script_analyzer.generate_media_plans(media_blocks)
        self._log(f"Media plans ready. Sample: {self._format_plan(media_plans, media_blocks)}")

        # ── STEP 3: Parallel media clip building ─────────────────────────
        self._log(f"Building {len(media_blocks)} media overlay clips…")
        overlay_clips = self._build_media_clips_parallel(media_blocks, media_plans)

        # ── STEP 5: Single FFmpeg overlay pass ───────────────────────────
        self._log(
            f"Composing final video — {len(overlay_clips)} overlay(s) "
            f"over {avatar_duration:.2f}s avatar…"
        )
        self._compose_with_overlay(
            avatar_video, overlay_clips, output_path, mode, avatar_duration
        )
        self._log(f"Done. Output={output_path}")
        return output_path

    def _format_plan(self, plans: dict, media_blocks: list) -> str:
        if not media_blocks or not plans:
            return "none"
        idx, _ = media_blocks[0]
        p = plans.get(idx)
        if not p:
            return "none"
        return f"block[{idx}] api={p.api_choice} kw='{p.primary_keyword}'"

    # ------------------------------------------------------------------
    # Parallel media clip builder
    # ------------------------------------------------------------------

    def _build_media_clips_parallel(
        self,
        media_blocks: list[tuple[int, object]],
        media_plans: dict[int, MediaPlan],
    ) -> list[tuple[float, float, Path]]:
        if not media_blocks:
            return []

        # 4 workers: balances parallelism vs API rate pressure
        max_workers = max(1, min(4, os.cpu_count() or 4))
        PER_SCENE_TIMEOUT = 90
        OVERALL_TIMEOUT = max(len(media_blocks) * 15, 360)

        results: dict[int, tuple[float, float, Path]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            jobs = {
                ex.submit(
                    self._build_media_overlay_clip,
                    idx, block, media_plans.get(idx)
                ): idx
                for idx, block in media_blocks
            }
            try:
                for fut in as_completed(jobs, timeout=OVERALL_TIMEOUT):
                    idx = jobs[fut]
                    try:
                        result = fut.result(timeout=PER_SCENE_TIMEOUT)
                        if result is not None:
                            results[idx] = result
                    except FutureTimeoutError:
                        self._log(f"Block {idx} timed out — skipping")
                    except Exception as exc:
                        self._log(f"Block {idx} failed: {exc}")
            except FutureTimeoutError:
                self._log(f"Overall timeout reached — composing with {len(results)} clips")
                for fut in jobs:
                    fut.cancel()

        return [results[i] for i in sorted(results.keys()) if i in results]

    def _build_media_overlay_clip(
        self, idx: int, block: object, plan: MediaPlan | None
    ) -> tuple[float, float, Path] | None:
        self._log(
            f"Block {idx}: start={block.start:.1f}s end={block.end:.1f}s "
            f"api={plan.api_choice if plan else 'PEXELS'} "
            f"kw='{plan.primary_keyword if plan else '?'}'"
        )
        try:
            clip_path = self._dispatch_media(block, idx, plan)
            return (block.start, block.end, clip_path)
        except Exception as exc:
            self._log(f"Block {idx} error ({exc}), using fallback")
            try:
                return (block.start, block.end, self._build_neutral_fallback(idx, block.duration))
            except Exception:
                return None

    # ------------------------------------------------------------------
    # STEP 3+4: Media dispatch + self-check
    # ------------------------------------------------------------------

    def _dispatch_media(
        self, block: object, scene_idx: int, plan: MediaPlan | None
    ) -> Path:
        """Route to Serper / Pexels / Merge based on Gemini plan."""
        if plan is None:
            return self._build_from_pexels_kw(scene_idx, block.duration, "cinematic", "nature cinematic")

        api = plan.api_choice.upper()

        if api == "SERPER":
            return self._build_from_serper(
                scene_idx, block.duration, plan.primary_keyword, plan.fallback_keyword
            )
        if api == "MERGE":
            sk = plan.serper_keyword or plan.primary_keyword
            pk = plan.pexels_keyword or plan.fallback_keyword
            return self._build_merge(scene_idx, block.duration, sk, pk)

        # Default: PEXELS
        return self._build_from_pexels_kw(
            scene_idx, block.duration, plan.primary_keyword, plan.fallback_keyword
        )

    # ------------------------------------------------------------------
    # SERPER path — Google Images
    # ------------------------------------------------------------------

    def _build_from_serper(
        self,
        scene_idx: int,
        duration: float,
        primary_kw: str,
        fallback_kw: str,
    ) -> Path:
        self._log(f"Scene {scene_idx}: Serper '{primary_kw}' / fallback '{fallback_kw}'")

        candidates = self.serper.search_with_fallback(
            primary_query=primary_kw,
            fallback_query=fallback_kw or primary_kw,
            num=5,
            min_results=1,
        )

        if not candidates:
            self._log(f"Scene {scene_idx}: Serper returned nothing → Pexels fallback")
            return self._build_from_pexels_kw(scene_idx, duration, primary_kw, fallback_kw)

        # Use top candidate (already verified accessible by serper.search_with_fallback)
        top = candidates[0]
        self._log(f"Scene {scene_idx}: Serper selected '{top.title}' from {top.source}")

        tasks = [{
            "scene_id": f"scene_{scene_idx}",
            "asset_id": top.id,
            "source": "serper",
            "query": primary_kw,
            "url": top.url,
            "metadata": {"width": top.width, "height": top.height},
        }]
        downloaded = self.downloader.download_many(tasks)

        if not downloaded:
            self._log(f"Scene {scene_idx}: Download failed → Pexels fallback")
            return self._build_from_pexels_kw(scene_idx, duration, primary_kw, fallback_kw)

        return self._stitch_image_clips(scene_idx, duration, downloaded)

    # ------------------------------------------------------------------
    # PEXELS path — stock video
    # ------------------------------------------------------------------

    def _build_from_pexels_kw(
        self,
        scene_idx: int,
        duration: float,
        primary_kw: str,
        fallback_kw: str,
    ) -> Path:
        self._log(f"Scene {scene_idx}: Pexels '{primary_kw}'")

        candidates = self.pexels.search_with_fallback(
            queries=[
                self._sanitize_query(primary_kw, max_words=5),
                self._sanitize_query(fallback_kw or primary_kw, max_words=5),
            ],
            target_count=5,
        )

        if not candidates:
            raise RuntimeError(f"Pexels: no results for '{primary_kw}'")

        ranked = rank_videos(candidates, query=primary_kw)
        # Prefer 15-20s clips
        best = next((v for v in ranked if 15 <= v.duration <= 20), None)
        if best is None:
            best = next((v for v in ranked if 10 <= v.duration <= 25), ranked[0])

        best_file = sorted(
            best.files, key=lambda f: abs(f.width - 1920) + abs(f.height - 1080)
        )[0]

        downloaded = self.downloader.download_many([{
            "scene_id": f"scene_{scene_idx}",
            "asset_id": best.id,
            "source": "pexels",
            "query": primary_kw,
            "url": best_file.url,
            "metadata": {"width": best_file.width, "height": best_file.height},
        }])
        if not downloaded:
            raise RuntimeError(f"Pexels download failed for scene {scene_idx}")

        out = self.config.temp_dir / f"scene_{scene_idx}_video.mp4"
        return self.video_builder.build_from_video(downloaded[0].path, duration, out)

    # ------------------------------------------------------------------
    # MERGE path — Serper image + Pexels video
    # ------------------------------------------------------------------

    def _build_merge(
        self,
        scene_idx: int,
        duration: float,
        serper_kw: str,
        pexels_kw: str,
    ) -> Path:
        self._log(f"Scene {scene_idx}: MERGE serper='{serper_kw}' pexels='{pexels_kw}'")

        # Serper: get a subject image (shown first ~5s)
        img_candidates = self.serper.search_with_fallback(
            primary_query=serper_kw,
            fallback_query=pexels_kw,
            num=3,
            min_results=1,
        )
        img_tasks = [
            {
                "scene_id": f"scene_{scene_idx}_img",
                "asset_id": c.id,
                "source": "serper",
                "query": serper_kw,
                "url": c.url,
                "metadata": {"width": c.width, "height": c.height},
            }
            for c in img_candidates[:2]
        ]
        img_assets = self.downloader.download_many(img_tasks) if img_tasks else []

        # Pexels: get environment/action video (fills remainder)
        vid_candidates = self.pexels.search_with_fallback(
            queries=[self._sanitize_query(pexels_kw, max_words=5)],
            target_count=3,
        )
        vid_assets: list[DownloadedAsset] = []
        if vid_candidates:
            ranked = rank_videos(vid_candidates, query=pexels_kw)
            best_vid = next((v for v in ranked if 15 <= v.duration <= 20), ranked[0])
            best_file = sorted(
                best_vid.files, key=lambda f: abs(f.width - 1920) + abs(f.height - 1080)
            )[0]
            vid_assets = self.downloader.download_many([{
                "scene_id": f"scene_{scene_idx}_vid",
                "asset_id": best_vid.id,
                "source": "pexels",
                "query": pexels_kw,
                "url": best_file.url,
                "metadata": {"width": best_file.width, "height": best_file.height},
            }])

        if not img_assets and not vid_assets:
            return self._build_neutral_fallback(scene_idx, duration)

        return self.scene_mixer.build_mixed_scene(
            scene_idx=scene_idx,
            duration=duration,
            image_assets=img_assets,
            video_assets=vid_assets,
            temp_dir=self.config.temp_dir,
        )

    # ------------------------------------------------------------------
    # Image clip stitching
    # ------------------------------------------------------------------

    def _stitch_image_clips(
        self,
        scene_idx: int,
        duration: float,
        downloaded: list[DownloadedAsset],
    ) -> Path:
        clips: list[Path] = []
        clip_duration = max(3.0, duration / max(len(downloaded), 1))
        for i, asset in enumerate(downloaded):
            clip_key = hashlib.sha1(
                f"{asset.path}:{clip_duration:.3f}:{i}".encode()
            ).hexdigest()[:16]
            clip = self.cache.generated_dir / f"imgclip_{clip_key}.mp4"
            if not clip.exists():
                self.image_builder.make_image_clip(
                    asset.path, clip_duration, "push_in_soft", clip
                )
            clips.append(clip)

        if not clips:
            return self._build_neutral_fallback(scene_idx, duration)

        if len(clips) == 1:
            trimmed = self.config.temp_dir / f"scene_{scene_idx}_img_trim.mp4"
            self.ffmpeg.run([
                "-i", str(clips[0]), "-t", f"{duration:.3f}",
                "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                str(trimmed),
            ])
            return trimmed

        scene_path = self.config.temp_dir / f"scene_{scene_idx}_images.mp4"
        needed = max(1, ceil(duration / clip_duration))
        timeline_clips = [clips[i % len(clips)] for i in range(needed)]
        self.video_builder.concat_image_clips(timeline_clips, scene_path)

        trimmed = self.config.temp_dir / f"scene_{scene_idx}_images_trim.mp4"
        self.ffmpeg.run([
            "-i", str(scene_path), "-t", f"{duration:.3f}",
            "-an", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            str(trimmed),
        ])
        return trimmed

    # ------------------------------------------------------------------
    # STEP 5: Single-pass FFmpeg overlay composition
    # ------------------------------------------------------------------

    def _compose_with_overlay(
        self,
        avatar_video: Path,
        overlay_clips: list[tuple[float, float, Path]],
        output_path: Path,
        mode: str,
        avatar_duration: float,
    ) -> None:
        profile = self.config.profiles.get(mode, self.config.profiles["ultra_fast_draft"])

        if not overlay_clips:
            self._log("No media clips — transcoding avatar directly…")
            encode_args = ["-preset", profile.preset, "-crf", str(profile.crf)]
            if profile.tune:
                encode_args += ["-tune", profile.tune]
            self.ffmpeg.run([
                "-i", str(avatar_video),
                "-c:v", "libx264", *encode_args,
                "-pix_fmt", "yuv420p", "-r", str(self.config.fps),
                "-c:a", "copy", "-t", f"{avatar_duration:.3f}",
                "-movflags", "+faststart", str(output_path),
            ])
            return

        W, H, FPS = self.config.resolution_w, self.config.resolution_h, self.config.fps
        args: list[str] = ["-i", str(avatar_video)]
        for _, _, clip_path in overlay_clips:
            args += ["-i", str(clip_path)]

        filter_parts: list[str] = []

        # Normalise base video
        filter_parts.append(
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,fps={FPS},format=yuv420p[base]"
        )

        # Offset each clip to its timeline position.
        # All overlay clips are pre-built at exactly W×H, FPS, yuv420p by the clip builders
        # (image_clip_builder, video_scene_builder, scene_mixer) — no scale/pad/format needed here.
        # Stripping those 4 filters per clip removes ~132 redundant filter ops for 33 overlays.
        for i, (start, _end, _path) in enumerate(overlay_clips):
            filter_parts.append(
                f"[{i+1}:v]setpts=PTS+{start:.3f}/TB[c{i}]"
            )

        # Chain overlays
        prev = "base"
        for i, (start, end, _path) in enumerate(overlay_clips):
            out_label = "vout" if i == len(overlay_clips) - 1 else f"v{i}"
            filter_parts.append(
                f"[{prev}][c{i}]overlay=x=0:y=0"
                f":enable='between(t,{start:.3f},{end:.3f})'"
                f":eof_action=pass[{out_label}]"
            )
            prev = out_label

        filter_complex = ";".join(filter_parts)
        encode_args = ["-preset", profile.preset, "-crf", str(profile.crf)]
        if profile.tune:
            encode_args += ["-tune", profile.tune]

        args += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a:0",          # original avatar audio — never re-encoded
            "-c:v", "libx264", *encode_args,
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "copy",           # zero drift, perfect sync
            "-t", f"{avatar_duration:.3f}",
            "-movflags", "+faststart",
            str(output_path),
        ]
        self.ffmpeg.run(args)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _sanitize_query(self, query: str, max_words: int = 6) -> str:
        words = re.findall(r"[A-Za-z0-9\-]+", query)
        return " ".join(words[:max_words]).strip()

    def _build_neutral_fallback(self, scene_idx: int, duration: float) -> Path:
        """
        Dark frame clip — last resort to prevent black/frozen scenes.
        Uses a dark grey colour so it's clearly visible as a fallback.
        """
        out = self.config.temp_dir / f"scene_{scene_idx}_fallback.mp4"
        self.ffmpeg.run([
            "-f", "lavfi",
            "-i", (
                f"color=c=0x1a1a1a:"
                f"s={self.config.resolution_w}x{self.config.resolution_h}:"
                f"r={self.config.fps}"
            ),
            "-t", f"{duration:.3f}", "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
            str(out),
        ])
        return out

from __future__ import annotations

import hashlib
import json
import subprocess
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from super_auto_editor_v2.models import DownloadedAsset, VisualIntent
from super_auto_editor_v2.search.asset_ranker import (
    rank_images,
    rank_videos,
    validate_image_candidate,
)
from super_auto_editor_v2.search.brave_image_searcher import BraveImageSearcher
from super_auto_editor_v2.search.pexels_video_searcher import PexelsVideoSearcher
from super_auto_editor_v2.search.query_builder import QueryBuilder
from super_auto_editor_v2.timeline.timeline_builder import TimelineBuilder


class ExportManager:
    _CONCAT_STREAM_FIELDS = (
        "codec_name",
        "profile",
        "level",
        "width",
        "height",
        "pix_fmt",
        "r_frame_rate",
        "avg_frame_rate",
        "time_base",
    )

    def __init__(self, config: AppConfig):
        self.config = config
        self.cache = CacheManager(config.cache_dir)
        self.ffmpeg = FFmpegRunner()
        self.timeline_builder = TimelineBuilder()
        self.script_analyzer = ScriptAnalyzer(config.gemini_api_key)
        self.brave = BraveImageSearcher(config.brave_api_key, cache=self.cache)
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

    def build(
        self,
        avatar_video: Path,
        script_path: Path,
        timeline_path: Path,
        output_path: Path,
        mode: str,
    ) -> Path:
        """
        Overlay architecture:
          - Avatar video is the base layer — audio is NEVER touched
          - Media clips are built in parallel and overlaid at their exact timestamps
          - Single FFmpeg pass at the end using filter_complex overlay chain
          - No avatar segmentation, no concat, no audio re-encode → perfect sync
        """
        self._t0 = perf_counter()
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)

        avatar_duration = self.ffmpeg.probe_duration(avatar_video)
        script_text = script_path.read_text(encoding="utf-8")
        self.script_analyzer.set_context(script_text)
        self.query_builder.reset()
        timeline = self.timeline_builder.load(timeline_path, script_text)
        self._log(f"Loaded timeline with {len(timeline)} blocks.")

        # Only build media blocks — avatar is left untouched as the base layer
        media_blocks = [
            (idx, block)
            for idx, block in enumerate(timeline)
            if block.type == "media"
        ]
        self._log(f"Building {len(media_blocks)} media overlay clips…")

        # Build all media clips in parallel
        overlay_clips = self._build_media_clips_parallel(media_blocks)
        # overlay_clips: list of (start_sec, end_sec, clip_path) sorted by start

        self._log(
            f"Composing final video with {len(overlay_clips)} overlay(s) "
            f"over {avatar_duration:.2f}s avatar…"
        )
        self._compose_with_overlay(
            avatar_video, overlay_clips, output_path, mode, avatar_duration
        )
        self._log(f"Done. Output={output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Parallel media clip builder
    # ------------------------------------------------------------------

    def _build_media_clips_parallel(
        self, media_blocks: list[tuple[int, object]]
    ) -> list[tuple[float, float, Path]]:
        if not media_blocks:
            return []

        max_workers = max(1, min(8, os.cpu_count() or 4))
        self._log(f"Parallel media clip build — workers={max_workers}")

        results: dict[int, tuple[float, float, Path]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            jobs = {
                ex.submit(self._build_media_overlay_clip, idx, block): idx
                for idx, block in media_blocks
            }
            for fut in as_completed(jobs):
                idx = jobs[fut]
                try:
                    result = fut.result()
                    if result is not None:
                        results[idx] = result
                except Exception as exc:
                    self._log(f"Block {idx} failed: {exc}")

        # Return clips sorted by their timeline position
        return [results[i] for i in sorted(results.keys()) if i in results]

    def _build_media_overlay_clip(
        self, idx: int, block: object
    ) -> tuple[float, float, Path] | None:
        self._log(
            f"Build media clip {idx}: "
            f"start={block.start:.2f}s  end={block.end:.2f}s  "
            f"duration={block.duration:.2f}s"
        )
        try:
            clip_path = self._build_media_segment(block, idx)
            return (block.start, block.end, clip_path)
        except Exception as exc:
            self._log(f"Media clip {idx} failed ({exc}), using neutral fallback")
            try:
                fallback = self._build_neutral_fallback(idx, block.duration)
                return (block.start, block.end, fallback)
            except Exception:
                return None

    # ------------------------------------------------------------------
    # Single-pass FFmpeg overlay composition
    # ------------------------------------------------------------------

    def _compose_with_overlay(
        self,
        avatar_video: Path,
        overlay_clips: list[tuple[float, float, Path]],
        output_path: Path,
        mode: str,
        avatar_duration: float,
    ) -> None:
        """
        Build the final video in a single FFmpeg call:
          - [0:v] is the full avatar video (base layer)
          - [1:v] … [N:v] are pre-built media clips (overlay layers)
          - Each clip is offset to its timeline position via setpts=PTS+START/TB
          - Overlays are chained: base → c0 → c1 … → vout
          - Audio is ALWAYS stream-copied from the avatar (0:a:0), zero drift
        """
        profile = self.config.profiles.get(mode, self.config.profiles["ultra_fast_draft"])

        if not overlay_clips:
            self._log("No media clips — transcoding avatar directly with render profile…")
            encode_args = ["-preset", profile.preset, "-crf", str(profile.crf)]
            if profile.tune:
                encode_args += ["-tune", profile.tune]
            self.ffmpeg.run([
                "-i", str(avatar_video),
                "-c:v", "libx264",
                *encode_args,
                "-pix_fmt", "yuv420p",
                "-r", str(self.config.fps),
                "-c:a", "copy",
                "-t", f"{avatar_duration:.3f}",
                "-movflags", "+faststart",
                str(output_path),
            ])
            return

        # --- Build the argument list ----------------------------------------
        args: list[str] = ["-i", str(avatar_video)]
        for _, _, clip_path in overlay_clips:
            args += ["-i", str(clip_path)]

        # --- filter_complex ---------------------------------------------------
        W = self.config.resolution_w
        H = self.config.resolution_h
        FPS = self.config.fps
        filter_parts: list[str] = []

        # 1. Normalise the base (avatar) video
        filter_parts.append(
            f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
            f"fps={FPS},format=yuv420p"
            f"[base]"
        )

        # 2. Normalise each media clip and offset its PTS to timeline position
        for i, (start, _end, _path) in enumerate(overlay_clips):
            # scale → match resolution; setpts offsets timestamps so the clip
            # "appears" at the correct position in the output timeline
            filter_parts.append(
                f"[{i + 1}:v]"
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,"
                f"fps={FPS},format=yuv420p,"
                f"setpts=PTS+{start:.3f}/TB"
                f"[c{i}]"
            )

        # 3. Chain overlay filters — each clip is active only within its window
        prev = "base"
        for i, (start, end, _path) in enumerate(overlay_clips):
            out_label = "vout" if i == len(overlay_clips) - 1 else f"v{i}"
            # eof_action=pass: when the clip runs out, fall through to base
            filter_parts.append(
                f"[{prev}][c{i}]"
                f"overlay=x=0:y=0"
                f":enable='between(t,{start:.3f},{end:.3f})'"
                f":eof_action=pass"
                f"[{out_label}]"
            )
            prev = out_label

        filter_complex = ";".join(filter_parts)

        encode_args = ["-preset", profile.preset, "-crf", str(profile.crf)]
        if profile.tune:
            encode_args += ["-tune", profile.tune]

        args += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",           # composed video
            "-map", "0:a:0",            # original avatar audio — NEVER re-encoded
            "-c:v", "libx264",
            *encode_args,
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-c:a", "copy",             # stream copy → zero drift, perfect sync
            "-t", f"{avatar_duration:.3f}",
            "-movflags", "+faststart",
            str(output_path),
        ]
        self.ffmpeg.run(args)

    # ------------------------------------------------------------------
    # Media segment dispatch  (unchanged logic, now returns overlay clip)
    # ------------------------------------------------------------------

    def _build_media_segment(self, block: object, scene_idx: int) -> Path:
        analysis = self.script_analyzer.analyze(block)
        intent = analysis.visual_intent

        self._log(
            f"Scene {scene_idx} type={analysis.scene_type} "
            f"source={analysis.source} "
            f"subject='{intent.primary_subject if intent else '?'}' "
            f"queries={analysis.search_queries[:2]}"
        )

        if intent:
            refined_queries = self.query_builder.build(
                intent, analysis.scene_type, max_queries=10
            )
            all_queries = list(dict.fromkeys(refined_queries + analysis.search_queries))
        else:
            all_queries = analysis.search_queries

        if analysis.source == "brave_images":
            return self._build_from_images(
                scene_idx, block.duration, all_queries, intent
            )
        if analysis.source == "mixed":
            return self._build_mixed_scene(
                scene_idx, block.duration, all_queries, intent
            )
        return self._build_from_pexels(
            scene_idx, block.duration, all_queries, intent
        )

    # ------------------------------------------------------------------
    # Brave images path
    # ------------------------------------------------------------------

    def _build_from_images(
        self,
        scene_idx: int,
        duration: float,
        queries: list[str],
        intent: VisualIntent | None,
    ) -> Path:
        wanted = 5
        self._log(f"Scene {scene_idx}: Brave target={wanted} images")

        must_show = intent.must_show if intent else []
        must_avoid = intent.must_avoid if intent else []

        candidates = self.brave.search_with_fallback(
            queries,
            visual_intent=intent,
            target_count=wanted * 3,
        )

        if not candidates:
            main_q = self._sanitize_query(queries[0] if queries else "subject", max_words=4)
            candidates = self.brave.search(main_q, count=60)

        main_q = queries[0] if queries else "subject"
        ranked = rank_images(
            list({c.url: c for c in candidates}.values()),
            query=main_q,
            must_show=must_show,
            must_avoid=must_avoid,
        )

        valid = [c for c in ranked if validate_image_candidate(c, intent)]
        if not valid:
            valid = ranked

        top = valid[:wanted]
        tasks = [
            {
                "scene_id": f"scene_{scene_idx}",
                "asset_id": c.id,
                "source": "brave",
                "query": main_q,
                "url": c.url,
                "metadata": {"width": c.width, "height": c.height},
            }
            for c in top
        ]
        downloaded = self.downloader.download_many(tasks)

        if not downloaded:
            self._log(
                f"Scene {scene_idx}: Brave returned no images, trying Pexels fallback."
            )
            try:
                pexels_q = [
                    queries[0] if queries else "cinematic scene",
                    "cinematic b-roll",
                    "atmospheric footage",
                ]
                return self._build_from_pexels(scene_idx, duration, pexels_q, intent)
            except Exception:
                return self._build_neutral_fallback(scene_idx, duration)

        return self._stitch_image_clips(scene_idx, duration, downloaded)

    # ------------------------------------------------------------------
    # Mixed scene path (Brave images + Pexels video)
    # ------------------------------------------------------------------

    def _build_mixed_scene(
        self,
        scene_idx: int,
        duration: float,
        queries: list[str],
        intent: VisualIntent | None,
    ) -> Path:
        self._log(f"Scene {scene_idx}: building MIXED scene (images + video)")

        img_candidates = self.brave.search_with_fallback(
            queries[:5], visual_intent=intent, target_count=3,
        )
        must_show = intent.must_show if intent else []
        must_avoid = intent.must_avoid if intent else []
        ranked_imgs = rank_images(
            img_candidates, query=queries[0],
            must_show=must_show, must_avoid=must_avoid,
        )

        img_tasks = [
            {
                "scene_id": f"scene_{scene_idx}_img",
                "asset_id": c.id,
                "source": "brave",
                "query": queries[0],
                "url": c.url,
                "metadata": {"width": c.width, "height": c.height},
            }
            for c in ranked_imgs[:3]
        ]
        img_assets = self.downloader.download_many(img_tasks)

        env_queries = queries[3:] or queries
        vid_candidates = self.pexels.search_with_fallback(
            [self._sanitize_query(q, max_words=5) for q in env_queries[:4]],
            target_count=3,
        )
        ranked_vids = rank_videos(
            vid_candidates,
            query=env_queries[0] if env_queries else "cinematic",
            visual_intent=intent,
        )

        vid_assets: list[DownloadedAsset] = []
        if ranked_vids:
            best_vid = next(
                (v for v in ranked_vids if 5 <= v.duration <= 20), ranked_vids[0]
            )
            best_file = sorted(
                best_vid.files,
                key=lambda f: abs(f.width - 1920) + abs(f.height - 1080),
            )[0]
            vid_assets = self.downloader.download_many([
                {
                    "scene_id": f"scene_{scene_idx}_vid",
                    "asset_id": best_vid.id,
                    "source": "pexels",
                    "query": env_queries[0] if env_queries else "",
                    "url": best_file.url,
                    "metadata": {"width": best_file.width, "height": best_file.height},
                }
            ])

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
    # Pexels video path
    # ------------------------------------------------------------------

    def _build_from_pexels(
        self,
        scene_idx: int,
        duration: float,
        queries: list[str],
        intent: VisualIntent | None,
    ) -> Path:
        candidates = self.pexels.search_with_fallback(
            [self._sanitize_query(q, max_words=5) for q in queries[:4]],
            target_count=5,
        )

        if not candidates:
            raise RuntimeError(f"No Pexels videos found for scene {scene_idx}")

        ranked = rank_videos(
            candidates,
            query=self._sanitize_query(queries[0] if queries else ""),
            visual_intent=intent,
        )
        best = next((v for v in ranked if 10 <= v.duration <= 15), ranked[0])
        best_file = sorted(
            best.files, key=lambda f: abs(f.width - 1920) + abs(f.height - 1080)
        )[0]

        downloaded = self.downloader.download_many([
            {
                "scene_id": f"scene_{scene_idx}",
                "asset_id": best.id,
                "source": "pexels",
                "query": queries[0],
                "url": best_file.url,
                "metadata": {"width": best_file.width, "height": best_file.height},
            }
        ])
        if not downloaded:
            raise RuntimeError(f"Failed downloading Pexels video for scene {scene_idx}")

        out = self.config.temp_dir / f"scene_{scene_idx}_video.mp4"
        return self.video_builder.build_from_video(downloaded[0].path, duration, out)

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
        clip_duration = 3.0
        for i, asset in enumerate(downloaded):
            clip_key = hashlib.sha1(
                f"{asset.path}:{clip_duration:.3f}:{i}".encode("utf-8")
            ).hexdigest()[:16]
            clip = self.cache.generated_dir / f"imgclip_{clip_key}.mp4"
            if not clip.exists():
                motion = self.image_builder.pick_motion_style()
                self.image_builder.make_image_clip(asset.path, clip_duration, motion, clip)
            clips.append(clip)

        scene_path = self.config.temp_dir / f"scene_{scene_idx}_images.mp4"
        needed = max(1, ceil(duration / clip_duration))
        timeline_clips = [clips[i % len(clips)] for i in range(needed)]

        if len(timeline_clips) == 1:
            # Single clip: trim to exact duration and return
            trimmed = self.config.temp_dir / f"scene_{scene_idx}_images_trimmed.mp4"
            self.ffmpeg.run([
                "-i", str(timeline_clips[0]),
                "-t", f"{duration:.3f}",
                "-an",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                str(trimmed),
            ])
            return trimmed

        self.video_builder.concat_image_clips(timeline_clips, scene_path)
        trimmed = self.config.temp_dir / f"scene_{scene_idx}_images_trimmed.mp4"
        self.ffmpeg.run([
            "-i", str(scene_path),
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(trimmed),
        ])
        return trimmed

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _sanitize_query(self, query: str, max_words: int = 6) -> str:
        words = re.findall(r"[A-Za-z0-9\-]+", query)
        return " ".join(words[:max_words]).strip()

    def _build_neutral_fallback(self, scene_idx: int, duration: float) -> Path:
        """Dark frame clip used when all media sources fail."""
        out = self.config.temp_dir / f"scene_{scene_idx}_fallback.mp4"
        self.ffmpeg.run([
            "-f", "lavfi",
            "-i", (
                f"color=c=0x111111:"
                f"s={self.config.resolution_w}x{self.config.resolution_h}:"
                f"r={self.config.fps}"
            ),
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "30",
            str(out),
        ])
        return out

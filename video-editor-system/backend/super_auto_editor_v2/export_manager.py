from __future__ import annotations

import hashlib
import json
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
        self._t0 = perf_counter()
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        avatar_duration = self.ffmpeg.probe_duration(avatar_video)
        script_text = script_path.read_text(encoding="utf-8")
        self.script_analyzer.set_context(script_text)
        self.query_builder.reset()
        timeline = self.timeline_builder.load(timeline_path, script_text)
        self._log(f"Loaded timeline with {len(timeline)} blocks.")

        segment_files = self._build_all_segments_parallel(timeline, avatar_video)

        video_only_raw = self.config.temp_dir / "video_only_raw.mp4"
        self._log("Concatenating timeline segments…")
        self._concat_segments(segment_files, video_only_raw)
        video_only = self.config.temp_dir / "video_only.mp4"
        self._fit_video_duration(video_only_raw, avatar_duration, video_only, avatar_video)
        self._log("Muxing avatar audio to final output…")
        self._mux_avatar_audio(avatar_video, video_only, output_path, mode, avatar_duration)
        self._log(f"Done. Output={output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Parallel segment builder
    # SPEED FIX: increased max_workers from 4 → 8
    # ------------------------------------------------------------------

    def _build_all_segments_parallel(self, timeline, avatar_video: Path) -> list[Path]:
        max_workers = max(1, min(8, os.cpu_count() or 4))
        self._log(f"Parallel segment build workers={max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            jobs = [
                ex.submit(self._build_block, idx, block, avatar_video)
                for idx, block in enumerate(timeline)
            ]
            outputs: dict[int, Path] = {}
            for fut in as_completed(jobs):
                idx, seg_path = fut.result()
                outputs[idx] = seg_path
        return [outputs[i] for i in sorted(outputs.keys())]

    def _build_block(self, idx: int, block, avatar_video: Path) -> tuple[int, Path]:
        seg_path = self.config.temp_dir / f"seg_{idx:04d}.mp4"
        self._log(
            f"Build block {idx}: type={block.type} "
            f"start={block.start:.2f} end={block.end:.2f}"
        )
        if block.type == "avatar":
            self._build_avatar_segment(avatar_video, block.start, block.duration, seg_path)
            return idx, seg_path
        media_segment = self._build_media_segment(block, idx)
        return idx, media_segment

    # ------------------------------------------------------------------
    # Media segment dispatch
    # ------------------------------------------------------------------

    def _build_media_segment(self, block, scene_idx: int) -> Path:
        analysis = self.script_analyzer.analyze(block)
        intent = analysis.visual_intent

        self._log(
            f"Scene {scene_idx} type={analysis.scene_type} "
            f"source={analysis.source} "
            f"subject='{intent.primary_subject if intent else '?'}' "
            f"queries={analysis.search_queries[:2]}"
        )

        # Build refined query list using QueryBuilder
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
                pexels_q = [queries[0] if queries else "cinematic scene",
                            "cinematic b-roll", "atmospheric footage"]
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
        ranked_imgs = rank_images(img_candidates, query=queries[0],
                                  must_show=must_show, must_avoid=must_avoid)

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

        if ranked_vids:
            best_vid = next((v for v in ranked_vids if 5 <= v.duration <= 20), ranked_vids[0])
            best_file = sorted(
                best_vid.files, key=lambda f: abs(f.width - 1920) + abs(f.height - 1080)
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
        else:
            vid_assets = []

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
            return timeline_clips[0]

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

    # SPEED + SYNC FIX: Stream copy when possible, minimal re-encode as fallback
    def _build_avatar_segment(
        self, avatar_video: Path, start: float, duration: float, out_path: Path
    ) -> None:
        """
        SPEED FIX: Try stream copy first (instant, no quality loss, perfect sync).
        Falls back to re-encode only if stream copy fails.
        """
        # Attempt 1: stream copy (10-100x faster, preserves exact timing)
        try:
            self.ffmpeg.run([
                "-ss", f"{start:.3f}",
                "-i", str(avatar_video),
                "-t", f"{duration:.3f}",
                "-c:v", "copy",
                "-an",
                str(out_path),
            ])
            return
        except Exception:
            pass  # Fall through to re-encode

        # Attempt 2: re-encode fallback (lower CRF=18 for better face quality)
        self.ffmpeg.run([
            "-ss", f"{start:.3f}",
            "-t", f"{duration:.3f}",
            "-i", str(avatar_video),
            "-an",
            "-vf", (
                f"scale={self.config.resolution_w}:{self.config.resolution_h},"
                f"fps={self.config.fps}"
            ),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            str(out_path),
        ])

    def _concat_segments(self, segments: list[Path], out_path: Path) -> None:
        """
        SPEED FIX: Try stream copy concat first (instant).
        Falls back to re-encode only when codecs differ.
        """
        filelist = self.config.temp_dir / "segments.txt"
        filelist.write_text(
            "\n".join(f"file '{s.as_posix()}'" for s in segments),
            encoding="utf-8",
        )

        can_copy_concat = self._can_concat_copy(segments)
        if can_copy_concat:
            # Attempt 1: stream copy (instant, no quality loss)
            try:
                self.ffmpeg.run([
                    "-f", "concat", "-safe", "0", "-i", str(filelist),
                    "-c", "copy",
                    "-an",
                    str(out_path),
                ])
                return
            except Exception as exc:
                self._log(
                    "concat_copy_failed reason=ffmpeg_error "
                    f"error={exc.__class__.__name__}; falling back to re-encode"
                )
                # Fall through to re-encode
        else:
            self._log("concat_copy_skipped reason=incompatible_streams")

        # Attempt 2: forced re-encode (compatible with all segment types)
        self.ffmpeg.run([
            "-f", "concat", "-safe", "0", "-i", str(filelist),
            "-an",
            "-vf", f"fps={self.config.fps},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-crf", "28",
            str(out_path),
        ])

    def _can_concat_copy(self, segments: list[Path]) -> bool:
        if not segments:
            self._log("concat_copy_skipped reason=no_segments")
            return False

        baseline_path = segments[0]
        baseline_stream = self._probe_video_stream_info(baseline_path)
        if baseline_stream is None:
            self._log(
                "concat_copy_skipped reason=probe_failed "
                f"segment={baseline_path.as_posix()}"
            )
            return False

        for segment in segments[1:]:
            stream = self._probe_video_stream_info(segment)
            if stream is None:
                self._log(
                    "concat_copy_skipped reason=probe_failed "
                    f"segment={segment.as_posix()}"
                )
                return False

            for field in self._CONCAT_STREAM_FIELDS:
                baseline_value = baseline_stream.get(field)
                current_value = stream.get(field)
                if baseline_value != current_value:
                    self._log(
                        "concat_copy_skipped reason=stream_mismatch "
                        f"field={field} baseline={baseline_value} "
                        f"current={current_value} segment={segment.as_posix()}"
                    )
                    return False
        return True

    def _probe_video_stream_info(self, segment: Path) -> dict[str, object] | None:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            f"stream={','.join(self._CONCAT_STREAM_FIELDS)}",
            "-of",
            "json",
            str(segment),
        ]
        try:
            raw = subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8")
            data = json.loads(raw)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
            self._log(
                "concat_copy_skipped reason=probe_exception "
                f"segment={segment.as_posix()} error={exc.__class__.__name__}"
            )
            return None

        streams = data.get("streams", [])
        if not streams:
            self._log(
                "concat_copy_skipped reason=no_video_stream "
                f"segment={segment.as_posix()}"
            )
            return None

        stream = streams[0]
        return {field: stream.get(field) for field in self._CONCAT_STREAM_FIELDS}

    def _fit_video_duration(
        self,
        video_in: Path,
        target_duration: float,
        out_path: Path,
        avatar_video: Path,
    ) -> None:
        current = self.ffmpeg.probe_duration(video_in)
        gap = target_duration - current
        if gap > 0.2:
            filler = self.config.temp_dir / "video_tail_filler.mp4"
            self._build_avatar_segment(avatar_video, current, gap, filler)
            list_file = self.config.temp_dir / "fit_concat.txt"
            list_file.write_text(
                "\n".join([
                    f"file '{video_in.as_posix()}'",
                    f"file '{filler.as_posix()}'",
                ]),
                encoding="utf-8",
            )
            # Try stream copy first for speed
            try:
                self.ffmpeg.run([
                    "-f", "concat", "-safe", "0", "-i", str(list_file),
                    "-c", "copy",
                    "-an",
                    "-t", f"{target_duration:.3f}",
                    str(out_path),
                ])
                return
            except Exception:
                pass

            self.ffmpeg.run([
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-an",
                "-vf", f"fps={self.config.fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-t", f"{target_duration:.3f}",
                str(out_path),
            ])
            return

        # Simple trim — try stream copy first
        try:
            self.ffmpeg.run([
                "-i", str(video_in),
                "-t", f"{target_duration:.3f}",
                "-c", "copy",
                "-an",
                str(out_path),
            ])
            return
        except Exception:
            pass

        self.ffmpeg.run([
            "-i", str(video_in),
            "-t", f"{target_duration:.3f}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out_path),
        ])

    def _mux_avatar_audio(
        self,
        avatar_video: Path,
        video_only: Path,
        output: Path,
        mode: str,
        target_duration: float,
    ) -> None:
        """
        SYNC FIX: Use -c:a copy (stream copy) so audio is NEVER re-encoded.
        Re-encoding audio shifts timestamps by tiny amounts that accumulate
        across the pipeline and cause lips to go out of sync.
        -shortest ensures we don't pad or cut when durations differ slightly.
        -avoid_negative_ts make_zero + -fflags +genpts fixes any stale timestamps.
        """
        profile = self.config.profiles.get(mode, self.config.profiles["ultra_fast_draft"])
        self.ffmpeg.run([
            "-i", str(video_only),
            "-i", str(avatar_video),
            "-map", "0:v:0",          # assembled video track
            "-map", "1:a:0",          # ORIGINAL avatar audio (untouched)
            "-c:v", "libx264",
            "-preset", profile.preset,
            "-crf", str(profile.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.config.fps),
            "-c:a", "copy",           # STREAM COPY — perfect sync, no drift
            "-shortest",              # end when shorter stream ends
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-movflags", "+faststart",
            str(output),
        ])

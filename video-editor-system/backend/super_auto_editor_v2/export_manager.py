from __future__ import annotations

import hashlib
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
from super_auto_editor_v2.media.video_scene_builder import VideoSceneBuilder
from super_auto_editor_v2.search.asset_ranker import rank_images, rank_videos
from super_auto_editor_v2.search.brave_image_searcher import BraveImageSearcher
from super_auto_editor_v2.search.pexels_video_searcher import PexelsVideoSearcher
from super_auto_editor_v2.timeline.timeline_builder import TimelineBuilder


class ExportManager:
    def __init__(self, config: AppConfig):
        self.config = config
        self.cache = CacheManager(config.cache_dir)
        self.ffmpeg = FFmpegRunner()
        self.timeline_builder = TimelineBuilder()
        self.script_analyzer = ScriptAnalyzer(config.gemini_api_key)
        self.brave = BraveImageSearcher(config.brave_api_key, cache=self.cache)
        self.pexels = PexelsVideoSearcher(config.pexels_api_key, cache=self.cache)
        self.downloader = Downloader(self.cache, workers=config.concurrency_downloads)
        self.image_builder = ImageClipBuilder(self.ffmpeg, config.resolution_w, config.resolution_h, config.fps)
        self.video_builder = VideoSceneBuilder(self.ffmpeg, config.resolution_w, config.resolution_h, config.fps)
        self._t0 = perf_counter()

    def _log(self, message: str) -> None:
        elapsed = perf_counter() - self._t0
        print(f"[SAE v2 +{elapsed:7.2f}s] {message}", flush=True)

    def build(self, avatar_video: Path, script_path: Path, timeline_path: Path, output_path: Path, mode: str) -> Path:
        self._t0 = perf_counter()
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        script_text = script_path.read_text(encoding="utf-8")
        timeline = self.timeline_builder.load(timeline_path, script_text)
        self._log(f"Loaded timeline with {len(timeline)} blocks.")

        segment_files = self._build_all_segments_parallel(timeline, avatar_video)

        video_only = self.config.temp_dir / "video_only.mp4"
        self._log("Concatenating timeline segments…")
        self._concat_segments(segment_files, video_only)
        self._log("Muxing avatar audio to final output…")
        self._mux_avatar_audio(avatar_video, video_only, output_path, mode)
        self._log(f"Done. Output={output_path}")
        return output_path

    def _build_all_segments_parallel(self, timeline, avatar_video: Path) -> list[Path]:
        jobs = []
        max_workers = max(1, min(4, os.cpu_count() or 2))
        self._log(f"Parallel segment build workers={max_workers}")
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for idx, block in enumerate(timeline):
                jobs.append(ex.submit(self._build_block, idx, block, avatar_video))
            outputs: dict[int, Path] = {}
            for fut in as_completed(jobs):
                idx, seg_path = fut.result()
                outputs[idx] = seg_path
        return [outputs[i] for i in sorted(outputs.keys())]

    def _build_block(self, idx: int, block, avatar_video: Path) -> tuple[int, Path]:
        seg_path = self.config.temp_dir / f"seg_{idx:04d}.mp4"
        self._log(f"Build block {idx}: type={block.type} start={block.start:.2f} end={block.end:.2f}")
        if block.type == "avatar":
            self._build_avatar_segment(avatar_video, block.start, block.duration, seg_path)
            return idx, seg_path
        media_segment = self._build_media_segment(block, idx)
        if media_segment != seg_path:
            # Fast remux to final segment filename (no extra effects pass).
            self.ffmpeg.run(["-i", str(media_segment), "-c", "copy", str(seg_path)])
        return idx, seg_path

    def _build_media_segment(self, block, scene_idx: int) -> Path:
        analysis = self.script_analyzer.analyze(block)
        # Guardrail: product/person-like phrases should not be routed to Pexels.
        if analysis.source == "pexels_video" and any(ch.isdigit() for ch in block.script_text):
            analysis.source = "brave_images"
        self._log(f"Scene {scene_idx} source={analysis.source} queries={analysis.search_queries[:2]}")
        if analysis.source == "brave_images":
            return self._build_from_images(scene_idx, block.duration, analysis.search_queries)
        return self._build_from_pexels(scene_idx, block.duration, analysis.search_queries)

    def _build_from_images(self, scene_idx: int, duration: float, queries: list[str]) -> Path:
        # Specific scenes target 15-20s visual rhythm: prefer 7 images when duration allows.
        if duration >= 15:
            wanted = min(self.config.brave_image_count_max, 7)
        else:
            wanted = min(self.config.brave_image_count_max, max(1, ceil(duration / self.config.image_duration_seconds)))
        self._log(f"Scene {scene_idx}: Brave target images={wanted}")
        candidates = []
        seen_queries = set()
        for q in queries[:7]:
            qn = q.strip()
            if not qn or qn.lower() in seen_queries:
                continue
            seen_queries.add(qn.lower())
            try:
                candidates.extend(self.brave.search(qn, count=20))
            except Exception as exc:
                self._log(f"Scene {scene_idx}: Brave query failed '{qn}' ({exc})")
                continue
            if len(candidates) >= wanted * 3:
                break
        ranked = rank_images(candidates, query=queries[0])[:wanted]
        tasks = [
            {
                "scene_id": f"scene_{scene_idx}",
                "asset_id": c.id,
                "source": "brave",
                "query": queries[0],
                "url": c.url,
                "metadata": {"width": c.width, "height": c.height},
            }
            for c in ranked
        ]
        downloaded = self.downloader.download_many(tasks)
        if not downloaded:
            self._log(f"Scene {scene_idx}: Brave returned no downloadable images, retrying relaxed query.")
            relaxed_q = " ".join((queries[0] if queries else "topic").split()[:2]).strip() or "topic"
            relaxed = self.brave.search(relaxed_q, count=30)
            relaxed_ranked = rank_images(relaxed, query=relaxed_q)[:wanted]
            downloaded = self.downloader.download_many([
                {
                    "scene_id": f"scene_{scene_idx}",
                    "asset_id": c.id,
                    "source": "brave",
                    "query": relaxed_q,
                    "url": c.url,
                    "metadata": {"width": c.width, "height": c.height},
                }
                for c in relaxed_ranked
            ])
        if not downloaded:
            self._log(f"Scene {scene_idx}: Brave fallback failed, creating neutral backup clip.")
            return self._build_neutral_fallback(scene_idx, duration)
        clips = []
        clip_duration = duration / max(1, len(downloaded))
        for i, asset in enumerate(downloaded):
            clip_key = hashlib.sha1(
                f"{asset.path}:{clip_duration:.3f}:{i}".encode("utf-8")
            ).hexdigest()[:16]
            clip = self.cache.generated_dir / f"imgclip_{clip_key}.mp4"
            motion = self.image_builder.pick_motion_style()
            # Uses lightweight scale/crop fake-zoom; much faster than zoompan.
            if not clip.exists():
                self.image_builder.make_image_clip(asset.path, clip_duration, motion, clip)
            clips.append(clip)

        scene_path = self.config.temp_dir / f"scene_{scene_idx}_images.mp4"
        if len(clips) == 1:
            return clips[0]
        self.video_builder.concat_image_clips(clips, scene_path)
        return scene_path

    def _build_neutral_fallback(self, scene_idx: int, duration: float) -> Path:
        out = self.config.temp_dir / f"scene_{scene_idx}_fallback.mp4"
        self.ffmpeg.run([
            "-f", "lavfi",
            "-i", f"color=c=0x111111:s={self.config.resolution_w}x{self.config.resolution_h}:r={self.config.fps}",
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "30",
            str(out),
        ])
        return out

    def _build_from_pexels(self, scene_idx: int, duration: float, queries: list[str]) -> Path:
        candidates = []
        for q in queries[:3]:
            candidates.extend(self.pexels.search(q, per_page=15))
            if candidates:
                break
        ranked = rank_videos(candidates, query=queries[0])
        if not ranked:
            raise RuntimeError(f"No pexels videos found for scene {scene_idx}")
        best = ranked[0]
        best_file = sorted(best.files, key=lambda v: abs(v.width - 1920) + abs(v.height - 1080))[0]
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
            raise RuntimeError(f"Failed downloading pexels video for scene {scene_idx}")
        out = self.config.temp_dir / f"scene_{scene_idx}_video.mp4"
        # Single-pass trim + scale + mute for speed.
        return self.video_builder.build_from_video(downloaded[0].path, duration, out)

    def _build_avatar_segment(self, avatar_video: Path, start: float, duration: float, out_path: Path) -> None:
        self.ffmpeg.run([
            "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(avatar_video),
            "-an",
            "-vf", f"scale={self.config.resolution_w}:{self.config.resolution_h},fps={self.config.fps}",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out_path),
        ])

    def _concat_segments(self, segments: list[Path], out_path: Path) -> None:
        filelist = self.config.temp_dir / "segments.txt"
        filelist.write_text("\n".join(f"file '{s.as_posix()}'" for s in segments), encoding="utf-8")
        self.ffmpeg.run([
            "-f", "concat", "-safe", "0", "-i", str(filelist),
            "-an", "-c:v", "copy", str(out_path),
        ])

    def _mux_avatar_audio(self, avatar_video: Path, video_only: Path, output: Path, mode: str) -> None:
        profile = self.config.profiles.get(mode, self.config.profiles["ultra_fast_draft"])
        # Keep avatar audio through full timeline; all media visuals are mute.
        self.ffmpeg.run([
            "-i", str(video_only),
            "-i", str(avatar_video),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", profile.preset,
            "-crf", str(profile.crf),
            "-pix_fmt", "yuv420p",
            "-r", str(self.config.fps),
            "-c:a", profile.audio_codec,
            "-movflags", "+faststart",
            "-shortest",
            str(output),
        ])

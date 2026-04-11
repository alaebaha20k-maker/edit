from __future__ import annotations

from math import ceil
from pathlib import Path

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

    def build(self, avatar_video: Path, script_path: Path, timeline_path: Path, output_path: Path, mode: str) -> Path:
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        script_text = script_path.read_text(encoding="utf-8")
        timeline = self.timeline_builder.load(timeline_path, script_text)

        segment_files: list[Path] = []
        for idx, block in enumerate(timeline):
            seg_path = self.config.temp_dir / f"seg_{idx:04d}.mp4"
            if block.type == "avatar":
                self._build_avatar_segment(avatar_video, block.start, block.duration, seg_path)
                segment_files.append(seg_path)
                continue
            media_segment = self._build_media_segment(block, idx)
            self._normalize_segment(media_segment, block.duration, seg_path)
            segment_files.append(seg_path)

        video_only = self.config.temp_dir / "video_only.mp4"
        self._concat_segments(segment_files, video_only)
        self._mux_avatar_audio(avatar_video, video_only, output_path, mode)
        return output_path

    def _build_media_segment(self, block, scene_idx: int) -> Path:
        analysis = self.script_analyzer.analyze(block)
        if analysis.source == "brave_images":
            return self._build_from_images(scene_idx, block.duration, analysis.search_queries)
        return self._build_from_pexels(scene_idx, block.duration, analysis.search_queries)

    def _build_from_images(self, scene_idx: int, duration: float, queries: list[str]) -> Path:
        wanted = min(self.config.brave_image_count_max, max(1, ceil(duration / self.config.image_duration_seconds)))
        candidates = []
        for q in queries[:3]:
            candidates.extend(self.brave.search(q, count=20))
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
        clips = []
        for i, asset in enumerate(downloaded):
            clip = self.config.temp_dir / f"scene_{scene_idx}_img_{i}.mp4"
            motion = self.image_builder.pick_motion_style()
            # Uses lightweight scale/crop fake-zoom; much faster than zoompan.
            self.image_builder.make_image_clip(asset.path, self.config.image_duration_seconds, motion, clip)
            clips.append(clip)

        scene_path = self.config.temp_dir / f"scene_{scene_idx}_images.mp4"
        if len(clips) == 1:
            return clips[0]
        self.video_builder.concat_image_clips(clips, scene_path)
        return scene_path

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

    def _normalize_segment(self, segment_path: Path, duration: float, out_path: Path) -> None:
        self.ffmpeg.run([
            "-i", str(segment_path),
            "-t", f"{duration:.3f}",
            "-an",
            "-vf", f"scale={self.config.resolution_w}:{self.config.resolution_h},fps={self.config.fps}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
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

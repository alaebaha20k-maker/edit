from __future__ import annotations

"""
scene_mixer.py
--------------
Combine Brave subject images + Pexels environment videos into a single
mixed-scene clip.

Strategy (interleaved):
  3s subject image → 4-5s environment video → 3s subject image → ...

This lets us show "Ford Focus 2024" (Brave image) while also showing
"driving on highway" (Pexels video) in the same scene segment.
"""

from math import ceil
from pathlib import Path

from super_auto_editor_v2.ffmpeg.runner import FFmpegRunner
from super_auto_editor_v2.models import DownloadedAsset


class SceneMixer:
    # Duration of each image segment in the mixed output
    IMAGE_CLIP_DURATION = 3.0
    # Max duration to take from each video clip
    VIDEO_CLIP_DURATION = 5.0

    def __init__(self, ffmpeg: FFmpegRunner, w: int, h: int, fps: int):
        self.ffmpeg = ffmpeg
        self.w = w
        self.h = h
        self.fps = fps

    def build_mixed_scene(
        self,
        scene_idx: int,
        duration: float,
        image_assets: list[DownloadedAsset],
        video_assets: list[DownloadedAsset],
        temp_dir: Path,
    ) -> Path:
        """
        Produce a single video file mixing images and videos.

        Falls back gracefully:
        - No images → pure video scene
        - No videos → pure image slideshow
        - Neither  → raises RuntimeError
        """
        if not image_assets and not video_assets:
            raise RuntimeError(f"SceneMixer: no assets for scene {scene_idx}")

        if not image_assets:
            return self._pure_video(scene_idx, duration, video_assets, temp_dir)

        if not video_assets:
            return self._pure_images(scene_idx, duration, image_assets, temp_dir)

        return self._mixed(scene_idx, duration, image_assets, video_assets, temp_dir)

    # ------------------------------------------------------------------
    # Mixed path
    # ------------------------------------------------------------------

    def _mixed(
        self,
        scene_idx: int,
        duration: float,
        images: list[DownloadedAsset],
        videos: list[DownloadedAsset],
        temp_dir: Path,
    ) -> Path:
        segments: list[Path] = []
        time_used = 0.0
        img_idx = 0
        vid_idx = 0
        seg_counter = 0

        while time_used < duration - 0.1:
            remaining = duration - time_used

            # Alternate: image first, then video
            use_image = (img_idx <= vid_idx) and (img_idx < len(images))
            use_video = not use_image and (vid_idx < len(videos))

            if use_image:
                clip_dur = min(self.IMAGE_CLIP_DURATION, remaining)
                asset = images[img_idx % len(images)]
                out = temp_dir / f"mix_{scene_idx}_img_{seg_counter}.mp4"
                self._image_to_clip(asset.path, clip_dur, out)
                segments.append(out)
                time_used += clip_dur
                img_idx += 1

            elif use_video:
                clip_dur = min(self.VIDEO_CLIP_DURATION, remaining)
                asset = videos[vid_idx % len(videos)]
                out = temp_dir / f"mix_{scene_idx}_vid_{seg_counter}.mp4"
                self._video_to_clip(asset.path, clip_dur, out)
                segments.append(out)
                time_used += clip_dur
                vid_idx += 1

            else:
                # Cycle back to the beginning
                img_idx = 0
                vid_idx = 0

            seg_counter += 1
            # Safety: prevent infinite loop if both lists exhausted somehow
            if seg_counter > 200:
                break

        if not segments:
            raise RuntimeError(f"SceneMixer: produced 0 segments for scene {scene_idx}")

        out_path = temp_dir / f"scene_{scene_idx}_mixed.mp4"
        if len(segments) == 1:
            return segments[0]

        return self._concat_and_trim(segments, duration, out_path)

    # ------------------------------------------------------------------
    # Pure fallbacks
    # ------------------------------------------------------------------

    def _pure_images(
        self,
        scene_idx: int,
        duration: float,
        images: list[DownloadedAsset],
        temp_dir: Path,
    ) -> Path:
        clips: list[Path] = []
        clip_dur = self.IMAGE_CLIP_DURATION
        needed = max(1, ceil(duration / clip_dur))
        for i in range(needed):
            asset = images[i % len(images)]
            out = temp_dir / f"mix_{scene_idx}_img_only_{i}.mp4"
            self._image_to_clip(asset.path, clip_dur, out)
            clips.append(out)

        out_path = temp_dir / f"scene_{scene_idx}_images_only.mp4"
        if len(clips) == 1:
            return clips[0]
        return self._concat_and_trim(clips, duration, out_path)

    def _pure_video(
        self,
        scene_idx: int,
        duration: float,
        videos: list[DownloadedAsset],
        temp_dir: Path,
    ) -> Path:
        out = temp_dir / f"scene_{scene_idx}_video_only.mp4"
        self._video_to_clip(videos[0].path, duration, out)
        return out

    # ------------------------------------------------------------------
    # FFmpeg helpers
    # ------------------------------------------------------------------

    def _image_to_clip(self, src: Path, duration: float, out: Path) -> None:
        """Convert a single image to a short video clip."""
        if out.exists() and out.stat().st_size > 0:
            return  # cache hit
        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"crop={self.w}:{self.h},"
            f"fps={self.fps},"
            f"format=yuv420p"
        )
        self.ffmpeg.run([
            "-loop", "1",
            "-framerate", "1",
            "-i", str(src),
            "-vf", vf,
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out),
        ])

    def _video_to_clip(self, src: Path, duration: float, out: Path) -> None:
        """Trim, scale, and mute a video clip."""
        if out.exists() and out.stat().st_size > 0:
            return  # cache hit
        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"crop={self.w}:{self.h},"
            f"fps={self.fps}"
        )
        self.ffmpeg.run([
            "-ss", "0",
            "-t", f"{duration:.3f}",
            "-i", str(src),
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out),
        ])

    def _concat_and_trim(
        self,
        segments: list[Path],
        total_duration: float,
        out: Path,
    ) -> Path:
        """Concatenate segments and trim to exact target duration."""
        valid = [p for p in segments if p.exists() and p.stat().st_size > 0]
        if not valid:
            raise RuntimeError("SceneMixer._concat_and_trim: no valid segments")

        list_file = out.with_suffix(".txt")
        list_file.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in valid),
            encoding="utf-8",
        )
        self.ffmpeg.run([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-t", f"{total_duration:.3f}",
            "-an",
            "-vf", f"fps={self.fps},format=yuv420p",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out),
        ])
        return out

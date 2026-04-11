from __future__ import annotations

import random
from pathlib import Path

from super_auto_editor_v2.ffmpeg.runner import FFmpegRunner


class ImageClipBuilder:
    def __init__(self, ffmpeg: FFmpegRunner, w: int, h: int, fps: int):
        self.ffmpeg = ffmpeg
        self.w = w
        self.h = h
        self.fps = fps

    def make_image_clip(self, image_path: Path, duration: float, motion_style: str, out_path: Path) -> Path:
        # Ultra-fast mode: disable motion transforms (they can slow long projects).
        del motion_style
        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"crop={self.w}:{self.h},fps={self.fps},format=yuv420p"
        )
        self.ffmpeg.run([
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(image_path),
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out_path),
        ])
        return out_path

    def pick_motion_style(self) -> str:
        return random.choice(["push_in_soft", "push_out_soft"])

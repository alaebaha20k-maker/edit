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
        d = max(duration, 0.1)

        # Static scale — no eval=frame, no zoompan, no per-frame expressions.
        # Both scale:eval=frame and zoompan hang on this Windows FFmpeg build.
        # force_original_aspect_ratio=increase + crop handles any source size
        # (thumbnails, portrait images, low-res downloads).
        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"crop={self.w}:{self.h},"
            f"fps={self.fps},format=yuv420p"
        )
        self.ffmpeg.run([
            "-loop", "1", "-t", f"{d:.3f}", "-i", str(image_path),
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

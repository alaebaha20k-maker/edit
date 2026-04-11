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
        # Speed-first fake zoom: animated scale (eval=frame), no zoompan.
        # This gives visible motion while staying lightweight.
        d = max(duration, 0.1)
        if motion_style == "push_out_soft":
            scale_expr = f"1.04-0.04*(t/{d:.4f})"
        else:
            scale_expr = f"1.00+0.04*(t/{d:.4f})"

        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"scale=trunc(iw*({scale_expr})/2)*2:trunc(ih*({scale_expr})/2)*2:eval=frame,"
            f"crop={self.w}:{self.h}:(in_w-{self.w})/2:(in_h-{self.h})/2,"
            f"fps={self.fps},format=yuv420p"
        )
        cmd = [
            "-loop", "1", "-t", f"{duration:.3f}", "-i", str(image_path),
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out_path),
        ]
        try:
            self.ffmpeg.run(cmd)
        except Exception:
            # Fast safe fallback if motion expression fails on edge-case images.
            self.ffmpeg.run([
                "-loop", "1", "-t", f"{duration:.3f}", "-i", str(image_path),
                "-vf", (
                    f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
                    f"crop={self.w}:{self.h},fps={self.fps},format=yuv420p"
                ),
                "-an",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                str(out_path),
            ])
        return out_path

    def pick_motion_style(self) -> str:
        return random.choice(["push_in_soft", "push_out_soft"])

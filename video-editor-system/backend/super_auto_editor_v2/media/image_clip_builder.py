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
        # Speed-first fake zoom: linear tiny scale animation through scale expression.
        if motion_style == "push_out_soft":
            scale_expr = "if(lte(t,0),1.03,1.03-0.01*(t/{d}))".format(d=max(duration, 0.1))
        else:
            scale_expr = "if(lte(t,0),1.00,1.00+0.01*(t/{d}))".format(d=max(duration, 0.1))

        vf = (
            f"scale=iw*{scale_expr}:ih*{scale_expr},"
            f"crop={self.w}:{self.h},"
            f"fps={self.fps},format=yuv420p"
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

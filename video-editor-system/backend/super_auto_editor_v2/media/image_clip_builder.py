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
            zoom_expr = f"1.04-0.04*(t/{d:.4f})"
        else:
            zoom_expr = f"1.00+0.04*(t/{d:.4f})"

        # cover = scale factor needed so the image fills the output canvas at minimum.
        # Handles images smaller than 1920x1080 (e.g. thumbnails, low-res downloads).
        # Uses if(gt(...)) instead of max() for Windows FFmpeg compatibility.
        # trunc(...//2)*2 forces even pixel dimensions required by libx264.
        cover = f"if(gt({self.w}/iw,{self.h}/ih),{self.w}/iw,{self.h}/ih)"
        scale_w = f"trunc(iw*({cover})*({zoom_expr})/2)*2"
        scale_h = f"trunc(ih*({cover})*({zoom_expr})/2)*2"

        vf = (
            f"scale={scale_w}:{scale_h}:eval=frame,"
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

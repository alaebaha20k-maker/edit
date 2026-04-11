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
        total_frames = max(1, int(round(d * self.fps)))

        if motion_style == "push_out_soft":
            # Zoom out: starts at 1.04x, ends at 1.00x.
            z_expr = f"1.04-0.04*on/{total_frames}"
        else:
            # Zoom in: starts at 1.00x, ends at 1.04x.
            z_expr = f"1.0+0.04*on/{total_frames}"

        # Three-stage filter — all compatible with Windows FFmpeg:
        # 1. scale: cover output canvas exactly (force_original_aspect_ratio handles
        #    any source size — thumbnails, portrait shots, wide images).
        # 2. crop: center-crop to exact 1920x1080.
        # 3. zoompan: animate the zoom using output frame number (on).
        #    zoompan is the FFmpeg-standard approach for image Ken Burns effect.
        #    It avoids scale:eval=frame, which on Windows FFmpeg cannot use the
        #    `t` timestamp variable for looped still-image inputs (t=0 always).
        # -r {fps} before -i forces the looped image to produce frames at the
        #    correct rate so zoompan:d and -t align exactly.
        vf = (
            f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,"
            f"crop={self.w}:{self.h},"
            f"zoompan=z='{z_expr}'"
            f":x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2'"
            f":d={total_frames}:s={self.w}x{self.h}:fps={self.fps},"
            f"format=yuv420p"
        )
        self.ffmpeg.run([
            "-loop", "1", "-r", str(self.fps), "-t", f"{d:.3f}", "-i", str(image_path),
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

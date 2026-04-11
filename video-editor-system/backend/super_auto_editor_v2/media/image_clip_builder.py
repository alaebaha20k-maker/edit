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

        # Use n (frame number 0,1,2,…) not t (timestamp).
        # For looped still images, t=0 for every frame unless -r is set on input;
        # n always increments correctly regardless of PTS.  -r fps below ensures both.
        if motion_style == "push_out_soft":
            zoom_expr = f"1.04-0.04*n/{total_frames}"
        else:
            zoom_expr = f"1.0+0.04*n/{total_frames}"

        # cover: scale factor so ANY source image fills the output canvas.
        # Uses if(gt()) not max() — unambiguous across all Windows FFmpeg builds.
        # trunc(…/2)*2 forces even pixel dimensions required by libx264.
        cover = f"if(gt({self.w}/iw,{self.h}/ih),{self.w}/iw,{self.h}/ih)"
        scale_w = f"trunc(iw*({cover})*({zoom_expr})/2)*2"
        scale_h = f"trunc(ih*({cover})*({zoom_expr})/2)*2"

        vf = (
            f"scale={scale_w}:{scale_h}:eval=frame,"
            f"crop={self.w}:{self.h},"
            f"fps={self.fps},format=yuv420p"
        )
        # -r fps before -i: forces the looped image to emit frames at the correct
        # rate so n increments in sync with real time (avoids t=0-for-all-frames).
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

from __future__ import annotations

from pathlib import Path

from super_auto_editor_v2.ffmpeg.runner import FFmpegRunner


class VideoSceneBuilder:
    def __init__(self, ffmpeg: FFmpegRunner, w: int, h: int, fps: int):
        self.ffmpeg = ffmpeg
        self.w = w
        self.h = h
        self.fps = fps

    def build_from_video(self, source: Path, duration: float, out_path: Path) -> Path:
        # Speed-first: single trim+scale pass and drop source audio immediately.
        vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},fps={self.fps}"
        self.ffmpeg.run([
            "-ss", "0", "-t", f"{duration:.3f}", "-i", str(source),
            "-vf", vf,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            str(out_path),
        ])
        return out_path

    def concat_image_clips(self, clips: list[Path], out_path: Path) -> Path:
        list_file = out_path.with_suffix(".txt")
        list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in clips), encoding="utf-8")
        self.ffmpeg.run([
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy",
            str(out_path),
        ])
        return out_path

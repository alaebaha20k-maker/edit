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
        # format=yuv420p ensures clip is composition-ready — no conversion needed in filter_complex
        vf = f"scale={self.w}:{self.h}:force_original_aspect_ratio=increase,crop={self.w}:{self.h},fps={self.fps},format=yuv420p"
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
        valid = [p for p in clips if p.exists() and p.stat().st_size > 0]
        if not valid:
            raise RuntimeError("No valid image clips available for concat.")
        if len(valid) == 1:
            return valid[0]

        list_file = out_path.with_suffix(".txt")
        list_file.write_text("\n".join(f"file '{p.as_posix()}'" for p in valid), encoding="utf-8")
        # Re-encode concat result for stability across image clips with small param differences.
        try:
            self.ffmpeg.run([
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-an",
                "-vf", f"fps={self.fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                str(out_path),
            ])
        except Exception:
            # Fallback path: use concat filter graph (more tolerant than concat demuxer).
            args: list[str] = []
            for p in valid:
                args.extend(["-i", str(p)])
            streams = "".join(f"[{i}:v:0]" for i in range(len(valid)))
            filter_graph = f"{streams}concat=n={len(valid)}:v=1:a=0[v]"
            args.extend([
                "-filter_complex", filter_graph,
                "-map", "[v]",
                "-an",
                "-vf", f"fps={self.fps},format=yuv420p",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                str(out_path),
            ])
            self.ffmpeg.run(args)
        return out_path

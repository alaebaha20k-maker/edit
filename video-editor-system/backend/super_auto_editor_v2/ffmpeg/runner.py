from __future__ import annotations

import subprocess
from pathlib import Path


class FFmpegRunner:
    def run(self, args: list[str]) -> None:
        # -threads 0 → use all available CPU cores for decoding and filter graph
        cmd = ["ffmpeg", "-y", "-threads", "0", *args]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def probe_duration(self, path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)

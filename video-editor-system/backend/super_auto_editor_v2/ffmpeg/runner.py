from __future__ import annotations

import subprocess
from pathlib import Path


class FFmpegRunner:
    def run(self, args: list[str]) -> None:
        cmd = ["ffmpeg", "-y", *args]
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            stderr_text = result.stderr.decode(errors="replace").strip()
            raise subprocess.CalledProcessError(result.returncode, cmd, stderr=stderr_text)

    def probe_duration(self, path: Path) -> float:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)

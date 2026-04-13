from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from super_auto_editor_v2.models import RenderProfile


@dataclass(slots=True)
class AppConfig:
    serper_api_key: str          # Google Images via serper.dev (replaces Brave)
    pexels_api_key: str
    gemini_api_key: str
    resolution_w: int
    resolution_h: int
    fps: int
    image_duration_seconds: float
    pexels_video_min_seconds: int
    pexels_video_max_seconds: int
    concurrency_downloads: int
    concurrency_search: int
    cache_dir: Path
    temp_dir: Path
    profiles: dict[str, RenderProfile]
    brave_api_key: str = ""      # kept for backward compat, no longer used


def load_config(config_path: Path | None = None) -> AppConfig:
    data = {}
    if config_path and config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))

    def env_or_data(env_key: str, data_key: str, default: str = "") -> str:
        return os.getenv(env_key, data.get(data_key, default))

    base_cache = Path(data.get("cache_dir", "./cache/super_auto_editor")).resolve()
    base_temp = Path(data.get("temp_dir", "./tmp/super_auto_editor")).resolve()
    profiles_data = data.get("profiles", {
        # Fastest possible — stream-copy concat, minimal encode passes
        "turbo": {"preset": "ultrafast", "crf": 28, "tune": "fastdecode"},
        # Good balance of speed + quality for most exports
        "ultra_fast_draft": {"preset": "ultrafast", "crf": 28},
        "fast_final": {"preset": "veryfast", "crf": 24},
        "quality_final": {"preset": "fast", "crf": 21},
    })

    profiles = {
        name: RenderProfile(
            preset=value.get("preset", "ultrafast"),
            crf=int(value.get("crf", 28)),
            tune=str(value.get("tune", "")),
        )
        for name, value in profiles_data.items()
    }

    return AppConfig(
        serper_api_key=env_or_data("SERPER_API_KEY", "serper_api_key"),
        pexels_api_key=env_or_data("PEXELS_API_KEY", "pexels_api_key"),
        gemini_api_key=env_or_data("GEMINI_API_KEY", "gemini_api_key"),
        brave_api_key=env_or_data("BRAVE_API_KEY", "brave_api_key"),  # legacy
        resolution_w=int(data.get("resolution_w", 1920)),
        resolution_h=int(data.get("resolution_h", 1080)),
        fps=int(data.get("fps", 30)),
        image_duration_seconds=float(data.get("image_duration_seconds", 3.0)),
        pexels_video_min_seconds=int(data.get("pexels_video_min_seconds", 5)),
        pexels_video_max_seconds=int(data.get("pexels_video_max_seconds", 20)),
        concurrency_downloads=int(data.get("concurrency_downloads", 8)),
        concurrency_search=int(data.get("concurrency_search", 6)),
        cache_dir=base_cache,
        temp_dir=base_temp,
        profiles=profiles,
    )

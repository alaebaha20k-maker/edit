from __future__ import annotations

from typing import Any

import requests

from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.models import VideoCandidate, VideoFileVariant


class PexelsVideoSearcher:
    BASE_URL = "https://api.pexels.com/videos/search"

    def __init__(self, api_key: str, cache: CacheManager, timeout: int = 10):
        self.api_key = api_key
        self.cache = cache
        self.timeout = timeout

    def search(self, query: str, per_page: int = 20) -> list[VideoCandidate]:
        cached = self.cache.load_search("pexels", query)
        payload = cached if cached else self._fetch(query=query, per_page=per_page)
        if not cached:
            self.cache.save_search("pexels", query, payload)
        return self._parse(payload)

    def _fetch(self, query: str, per_page: int) -> dict[str, Any]:
        headers = {"Authorization": self.api_key}
        params = {"query": query, "per_page": per_page, "orientation": "landscape"}
        r = requests.get(self.BASE_URL, headers=headers, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _parse(self, payload: dict[str, Any]) -> list[VideoCandidate]:
        out: list[VideoCandidate] = []
        for item in payload.get("videos", []):
            files = []
            for vfile in item.get("video_files", []):
                if vfile.get("width", 0) < 640:
                    continue
                files.append(
                    VideoFileVariant(
                        url=vfile.get("link", ""),
                        width=int(vfile.get("width") or 0),
                        height=int(vfile.get("height") or 0),
                        fps=float(vfile.get("fps") or 30),
                    )
                )
            if not files:
                continue
            out.append(
                VideoCandidate(
                    id=str(item.get("id")),
                    duration=float(item.get("duration") or 0),
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    files=files,
                )
            )
        return out

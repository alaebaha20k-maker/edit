from __future__ import annotations

from typing import Any

import requests

from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.models import ImageCandidate


class BraveImageSearcher:
    BASE_URL = "https://api.search.brave.com/res/v1/images/search"

    def __init__(self, api_key: str, cache: CacheManager, timeout: int = 10):
        self.api_key = api_key
        self.cache = cache
        self.timeout = timeout

    def search(self, query: str, count: int = 20) -> list[ImageCandidate]:
        cached = self.cache.load_search("brave", query)
        payload = cached if cached else self._fetch(query=query, count=count)
        if not cached:
            self.cache.save_search("brave", query, payload)
        return self._parse(payload)

    def _fetch(self, query: str, count: int) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {"q": query, "count": count}
        r = requests.get(self.BASE_URL, headers=headers, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _parse(self, payload: dict[str, Any]) -> list[ImageCandidate]:
        out: list[ImageCandidate] = []
        for idx, item in enumerate(payload.get("results", [])):
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            if width < 1000 or height < 500:
                continue
            url = item.get("properties", {}).get("url") or item.get("url")
            if not url:
                continue
            out.append(
                ImageCandidate(
                    id=str(item.get("id") or f"brave_{idx}"),
                    url=url,
                    title=item.get("title", ""),
                    width=width,
                    height=height,
                )
            )
        return out

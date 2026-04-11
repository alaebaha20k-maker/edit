from __future__ import annotations

import threading
import time
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
        self._lock = threading.Lock()
        self._last_call_ts = 0.0
        self._min_interval_sec = 0.35  # soft client throttle to reduce 429 bursts

    def search(self, query: str, count: int = 20) -> list[ImageCandidate]:
        if not query or len(query.strip()) < 3:
            return []
        cached = self.cache.load_search("brave", query)
        payload = cached if cached else self._fetch_with_retry(query=query, count=count)
        if payload is None:
            return []
        if not cached:
            self.cache.save_search("brave", query, payload)
        return self._parse(payload)

    def _fetch_with_retry(self, query: str, count: int) -> dict[str, Any] | None:
        backoff = 1.0
        for _ in range(4):
            try:
                return self._fetch(query=query, count=count)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status != 429:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
            except requests.RequestException:
                time.sleep(backoff)
                backoff = min(backoff * 2, 8.0)
        return None

    def _fetch(self, query: str, count: int) -> dict[str, Any]:
        with self._lock:
            now = time.time()
            delta = now - self._last_call_ts
            if delta < self._min_interval_sec:
                time.sleep(self._min_interval_sec - delta)
            self._last_call_ts = time.time()
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
            props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
            url_candidates = [
                props.get("url"),
                props.get("image_url"),
                item.get("url"),
                item.get("image_url"),
                item.get("thumbnail"),
            ]
            url = next((u for u in url_candidates if isinstance(u, str) and u.startswith("http")), "")
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

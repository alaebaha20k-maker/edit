from __future__ import annotations

import threading
import time
import re
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
        if cached:
            return self._parse(cached)
        results = self._fetch_paginated(query=query, total_count=count)
        self.cache.save_search("brave", query, {"results": results})
        return self._parse({"results": results})

    def _fetch_paginated(self, query: str, total_count: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page_size = min(100, max(20, total_count))
        max_pages = 3
        for page in range(max_pages):
            offset = page * page_size
            payload = self._fetch_with_retry(query=query, count=page_size, offset=offset)
            if not payload:
                continue
            results = payload.get("results", [])
            if not results:
                break
            out.extend(results)
            if len(out) >= total_count:
                break
        return out

    def _fetch_with_retry(self, query: str, count: int, offset: int = 0) -> dict[str, Any] | None:
        backoff = 1.0
        for _ in range(4):
            try:
                return self._fetch(query=query, count=count, offset=offset)
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

    def _fetch(self, query: str, count: int, offset: int = 0) -> dict[str, Any]:
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
        params = {"q": query, "count": count, "offset": offset, "safesearch": "off"}
        r = requests.get(self.BASE_URL, headers=headers, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _parse(self, payload: dict[str, Any]) -> list[ImageCandidate]:
        out: list[ImageCandidate] = []
        for idx, item in enumerate(payload.get("results", [])):
            width = int(item.get("width") or 0)
            height = int(item.get("height") or 0)
            props = item.get("properties", {}) if isinstance(item.get("properties"), dict) else {}
            url_candidates = [
                item.get("image_url"),
                props.get("image_url"),
                props.get("url"),
                item.get("url"),
                item.get("thumbnail"),
            ]
            url = next((u for u in url_candidates if self._is_direct_image_url(u)), "")
            if not url:
                page_url = item.get("url") if isinstance(item.get("url"), str) else ""
                if page_url.startswith("http"):
                    extracted = self._extract_image_from_page(page_url)
                    if extracted:
                        url = extracted
            if not url:
                continue
            if width and height and (width < 640 or height < 360):
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

    def _is_direct_image_url(self, url: Any) -> bool:
        if not isinstance(url, str) or not url.startswith("http"):
            return False
        lower = url.lower().split("?", 1)[0]
        return lower.endswith((".jpg", ".jpeg", ".png", ".webp"))

    def _extract_image_from_page(self, page_url: str) -> str | None:
        try:
            r = requests.get(page_url, timeout=4)
            if r.status_code != 200:
                return None
            html = r.text[:200000]
            matches = re.findall(r"<img[^>]+src=[\"']([^\"']+)[\"']", html, flags=re.IGNORECASE)
            for m in matches:
                if self._is_direct_image_url(m):
                    return m
        except Exception:
            return None
        return None

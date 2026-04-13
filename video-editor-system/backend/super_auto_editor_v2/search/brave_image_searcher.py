from __future__ import annotations

import re
import threading
import time
from typing import Any

import requests

from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.models import ImageCandidate, VisualIntent
from super_auto_editor_v2.search.asset_ranker import calculate_relevance


class BraveImageSearcher:
    BASE_URL = "https://api.search.brave.com/res/v1/images/search"

    # Minimum dimension requirements — reject anything below 720p
    MIN_WIDTH = 1280
    MIN_HEIGHT = 720

    # URL patterns for trusted image CDNs (used as fallback when no extension)
    TRUSTED_CDN_PATTERNS = [
        "images.unsplash.", "pbs.twimg.", "i.imgur.", "upload.wikimedia.",
        "media.gettyimages.", "images.pexels.", "cdn.pixabay.",
        "staticflickr.", "live.staticflickr.", "i.pinimg.",
        "motortrend.", "caranddriver.", "netcarshow.", "autoblog.",
    ]

    # URL fragments that indicate icons / logos / tiny images
    BAD_URL_FRAGMENTS = [
        "icon", "logo", "avatar", "thumbnail", "favicon",
        "1x1", "pixel", "placeholder", "badge", "emoji",
        "sprite", "button", "banner-small",
    ]

    def __init__(self, api_key: str, cache: CacheManager, timeout: int = 10):
        self.api_key = api_key
        self.cache = cache
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last_call_ts = 0.0
        self._min_interval_sec = 0.25
        # Limit concurrent HTTP requests to 3 regardless of how many threads call us.
        # Without this, 80+ parallel scenes all blast the API simultaneously → 429 storm
        # → 4-retry backoff → each thread waits 30+ seconds → 10-minute hangs.
        self._http_semaphore = threading.Semaphore(3)

    def search(self, query: str, count: int = 20) -> list[ImageCandidate]:
        if not query or len(query.strip()) < 3:
            return []
        cached = self.cache.load_search("brave", query)
        if cached:
            return self._parse(cached)
        with self._http_semaphore:   # cap to 3 concurrent HTTP calls
            results = self._fetch_paginated(query=query, total_count=count)
        self.cache.save_search("brave", query, {"results": results})
        return self._parse({"results": results})

    def search_with_fallback(
        self,
        queries: list[str],
        visual_intent: VisualIntent | None = None,
        target_count: int = 5,
    ) -> list[ImageCandidate]:
        """
        Try multiple queries in order until we have enough relevant results.
        Each query's results are relevance-filtered before counting toward target.
        """
        all_candidates: list[ImageCandidate] = []
        seen_urls: set[str] = set()
        subject = (visual_intent.primary_subject or "") if visual_intent else ""
        must_show = (visual_intent.must_show or []) if visual_intent else []
        must_avoid = (visual_intent.must_avoid or []) if visual_intent else []

        for query in queries:
            if len(all_candidates) >= target_count:
                break

            raw = self.search(query, count=20)

            for candidate in raw:
                if candidate.url in seen_urls:
                    continue
                seen_urls.add(candidate.url)

                # Relevance gate
                text = f"{candidate.title} {candidate.url}"
                relevance, _ = calculate_relevance(text, subject or query, must_show, must_avoid)
                if relevance < 0.08:
                    continue

                candidate.relevance_score = relevance
                all_candidates.append(candidate)

        # Sort by relevance then return top N
        all_candidates.sort(key=lambda c: c.relevance_score, reverse=True)
        return all_candidates[:target_count]

    # ------------------------------------------------------------------
    # Internal fetch helpers
    # ------------------------------------------------------------------

    def _fetch_paginated(self, query: str, total_count: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        page_size = min(100, max(20, total_count))
        payload = self._fetch_with_retry(query=query, count=page_size, offset=0)
        if payload:
            out.extend(payload.get("results", []))
        return out

    def _fetch_with_retry(self, query: str, count: int, offset: int = 0) -> dict[str, Any] | None:
        backoff = 1.0
        for _ in range(2):   # 2 retries max (was 4) — fail fast, move to next query
            try:
                return self._fetch(query=query, count=count, offset=offset)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                if status != 429:
                    raise
                time.sleep(backoff)
                backoff = min(backoff * 2, 4.0)   # max 4s backoff (was 8s)
            except requests.RequestException:
                time.sleep(backoff)
                backoff = min(backoff * 2, 4.0)
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

    # ------------------------------------------------------------------
    # Parse & validate
    # ------------------------------------------------------------------

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
            url = next((u for u in url_candidates if self._is_valid_image_url(u)), "")
            if not url:
                continue

            # Dimension filter
            if width and height and (width < self.MIN_WIDTH or height < self.MIN_HEIGHT):
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

    def _is_valid_image_url(self, url: Any) -> bool:
        """Strict validation: direct image URLs only, no icons/logos."""
        if not isinstance(url, str) or not url.startswith("http"):
            return False

        # Strip query string for extension check
        clean = url.lower().split("?", 1)[0]

        # Check for bad fragments
        for frag in self.BAD_URL_FRAGMENTS:
            if frag in clean:
                return False

        # Direct image extension
        if any(clean.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp")):
            return True

        # Trusted CDN without extension is acceptable
        if any(cdn in clean for cdn in self.TRUSTED_CDN_PATTERNS):
            return True

        return False

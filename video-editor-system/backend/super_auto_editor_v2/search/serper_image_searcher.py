from __future__ import annotations

"""
serper_image_searcher.py
------------------------
Google Images search via serper.dev API.
Replaces BraveImageSearcher — Google Images has vastly better relevance
than Brave for specific product/brand/person searches.

Strategy:
  1. POST to https://google.serper.dev/images with primary_keyword
  2. Filter results: bad domains, merch/anime title terms, dimension floor
  3. Self-check: HEAD request confirms URL is accessible and content-type is image
  4. If < min_results usable images, retry with fallback_keyword
"""

import re
import threading
import time
from typing import Any

import requests

from super_auto_editor_v2.cache.cache_manager import CacheManager
from super_auto_editor_v2.models import ImageCandidate


class SerperImageSearcher:
    BASE_URL = "https://google.serper.dev/images"

    # Minimum dimensions — accept anything ≥ 800×450 (roughly 720p-class)
    MIN_WIDTH = 800
    MIN_HEIGHT = 450

    # Source domains that consistently return garbage (merch, fan-art, etc.)
    BAD_DOMAINS: frozenset[str] = frozenset({
        "redbubble.com", "teepublic.com", "zazzle.com", "spreadshirt.com",
        "cafepress.com", "teespring.com", "printful.com", "merch.amazon.com",
        "deviantart.com", "artstation.com", "pixiv.net", "zerochan.net",
        "myanimelist.net", "danbooru.donmai.us",
        "amazon.com", "ebay.com", "etsy.com",  # product listings, not photos
    })

    # URL path fragments that indicate junk images
    BAD_URL_FRAGMENTS: list[str] = [
        "t-shirt", "tshirt", "hoodie", "sticker", "mug", "poster",
        "merch", "merchandise", "anime", "manga", "cartoon",
        "phone-case", "phonecase", "pillow", "wallpaper",
    ]

    # Title terms that indicate art/merch — rejected even if URL looks OK
    BAD_TITLE_TERMS: list[str] = [
        "anime", "manga", "fan art", "fanart", "chibi", "cartoon",
        "illustration", "drawing", "clipart", "vector", "pixel art",
        "t-shirt", "tshirt", "hoodie", "sticker", "poster", "mug",
        "merch", "merchandise", "redbubble", "teepublic",
        "free download", "wallpaper hd",
    ]

    def __init__(self, api_key: str, cache: CacheManager, timeout: int = 10):
        self.api_key = api_key
        self.cache = cache
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last_call_ts = 0.0
        self._min_interval_sec = 0.30
        # Cap concurrent HTTP calls — Google Serper is rate-limited
        self._http_semaphore = threading.Semaphore(3)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search(self, query: str, num: int = 5) -> list[ImageCandidate]:
        """Search Google Images via Serper. Results are cached."""
        if not query or len(query.strip()) < 3:
            return []
        cached = self.cache.load_search("serper", query)
        if cached:
            return self._parse(cached)
        with self._http_semaphore:
            payload = self._fetch(query=query, num=num)
        if payload:
            self.cache.save_search("serper", query, payload)
            return self._parse(payload)
        return []

    def search_with_fallback(
        self,
        primary_query: str,
        fallback_query: str,
        num: int = 5,
        min_results: int = 1,
    ) -> list[ImageCandidate]:
        """
        Try primary_query first.
        If fewer than min_results pass local quality checks, try fallback_query.
        Self-verifies top result accessibility before returning.
        """
        results = self.search(primary_query, num=num)
        good = [c for c in results if self._passes_local_checks(c)]

        if len(good) < min_results:
            results2 = self.search(fallback_query, num=num)
            good2 = [c for c in results2 if self._passes_local_checks(c)]
            # Merge deduplicated
            seen = {c.url for c in good}
            combined = good + [c for c in good2 if c.url not in seen]
            good = combined if combined else (results + results2)

        # Self-check: verify top candidate is actually accessible
        verified: list[ImageCandidate] = []
        for c in good[:num]:
            if self._verify_accessible(c.url):
                verified.append(c)

        return verified if verified else good  # fallback to unverified if all fail

    # ------------------------------------------------------------------
    # Internal fetch
    # ------------------------------------------------------------------

    def _fetch(self, query: str, num: int) -> dict[str, Any] | None:
        with self._lock:
            now = time.time()
            delta = now - self._last_call_ts
            if delta < self._min_interval_sec:
                time.sleep(self._min_interval_sec - delta)
            self._last_call_ts = time.time()

        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query, "num": num}
        try:
            r = requests.post(
                self.BASE_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Parse & filter
    # ------------------------------------------------------------------

    def _parse(self, payload: dict[str, Any]) -> list[ImageCandidate]:
        out: list[ImageCandidate] = []
        for idx, item in enumerate(payload.get("images", [])):
            url = item.get("imageUrl", "")
            if not url or not url.startswith("http"):
                continue

            title = str(item.get("title") or "")
            source = str(item.get("source") or "")
            width = int(item.get("imageWidth") or 0)
            height = int(item.get("imageHeight") or 0)

            # Domain gate
            if any(bad in source.lower() for bad in self.BAD_DOMAINS):
                continue

            # URL fragment gate
            url_lower = url.lower()
            if any(frag in url_lower for frag in self.BAD_URL_FRAGMENTS):
                continue

            # Title gate
            title_lower = title.lower()
            if any(term in title_lower for term in self.BAD_TITLE_TERMS):
                continue

            # Dimension gate (skip only if dimensions are known AND too small)
            if width and height:
                if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                    continue

            out.append(ImageCandidate(
                id=f"serper_{idx}",
                url=url,
                title=title,
                width=width,
                height=height,
                source=source,
            ))
        return out

    def _passes_local_checks(self, c: ImageCandidate) -> bool:
        """Fast local quality check — no network requests."""
        title_lower = c.title.lower()
        if any(term in title_lower for term in self.BAD_TITLE_TERMS):
            return False
        url_lower = c.url.lower()
        if any(frag in url_lower for frag in self.BAD_URL_FRAGMENTS):
            return False
        return True

    def _verify_accessible(self, url: str) -> bool:
        """
        HEAD request to confirm image URL is reachable and serves image content.
        Times out quickly (5s) to keep the pipeline fast.
        """
        try:
            r = requests.head(url, timeout=5, allow_redirects=True)
            ct = r.headers.get("content-type", "")
            return r.status_code == 200 and "image" in ct.lower()
        except Exception:
            return False

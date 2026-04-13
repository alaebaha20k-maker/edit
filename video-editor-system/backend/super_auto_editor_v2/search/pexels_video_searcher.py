from __future__ import annotations

import re
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
        if not query or len(query.strip()) < 2:
            return []
        cached = self.cache.load_search("pexels", query)
        payload = cached if cached else self._fetch(query=query, per_page=per_page)
        if not cached:
            self.cache.save_search("pexels", query, payload)
        return self._parse(payload)

    def search_with_fallback(
        self,
        queries: list[str],
        target_count: int = 3,
        per_page: int = 15,
    ) -> list[VideoCandidate]:
        """
        Try multiple queries until we accumulate *target_count* candidates.
        Deduplicates by video ID across queries.
        """
        all_candidates: list[VideoCandidate] = []
        seen_ids: set[str] = set()

        for query in queries:
            if len(all_candidates) >= target_count:
                break
            results = self.search(query, per_page=per_page)
            for vid in results:
                if vid.id not in seen_ids:
                    seen_ids.add(vid.id)
                    all_candidates.append(vid)

        return all_candidates

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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
                if int(vfile.get("width", 0) or 0) < 1280:
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

            # Extract tags from multiple Pexels response fields
            tags = self._extract_tags(item)

            out.append(
                VideoCandidate(
                    id=str(item.get("id")),
                    duration=float(item.get("duration") or 0),
                    width=int(item.get("width") or 0),
                    height=int(item.get("height") or 0),
                    files=files,
                    tags=tags,
                )
            )
        return out

    def _extract_tags(self, item: dict[str, Any]) -> list[str]:
        """
        Extract keyword tags from a Pexels video result.
        Pexels exposes tags under different keys depending on API version.
        We also mine the video URL and photographer name for extra signal.
        """
        tags: list[str] = []

        # Official tags field (present in some Pexels responses)
        raw_tags = item.get("tags") or []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                if isinstance(t, str):
                    tags.append(t.lower())
                elif isinstance(t, dict):
                    label = t.get("label") or t.get("name") or t.get("title") or ""
                    if label:
                        tags.append(str(label).lower())

        # Mine the video URL for context words
        url = item.get("url") or ""
        if isinstance(url, str):
            # Pexels video URLs like: /video/ford-focus-driving-1234567/
            slug_words = re.findall(r"[a-z][a-z0-9]+", url.lower())
            noise = {"video", "videos", "pexels", "com", "www", "https", "http",
                     "free", "stock", "footage", "hd", "4k", "download"}
            tags.extend(w for w in slug_words if w not in noise and len(w) > 2)

        # Photographer name (weak signal but sometimes useful)
        photographer = item.get("photographer") or ""
        if isinstance(photographer, str):
            name_words = re.findall(r"[a-z]+", photographer.lower())
            tags.extend(w for w in name_words if len(w) > 3)

        # Deduplicate while preserving order
        seen: set[str] = set()
        result: list[str] = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                result.append(t)

        return result

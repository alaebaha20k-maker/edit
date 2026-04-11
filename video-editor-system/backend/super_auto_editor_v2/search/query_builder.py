from __future__ import annotations

"""
query_builder.py
----------------
Builds ranked search query lists from a VisualIntent.

Rules:
- Specific scenes: most-specific queries first (brand+model+year+action)
- General scenes: mood/atmosphere queries for Pexels B-roll
- Mixed scenes: both specific subject + supporting environment queries
- Deduplication across a session to avoid redundant API calls
"""

import re

from super_auto_editor_v2.models import VisualIntent


class QueryBuilder:
    def __init__(self) -> None:
        self._used: set[str] = set()

    def reset(self) -> None:
        """Clear session dedup cache."""
        self._used.clear()

    def build(
        self,
        intent: VisualIntent,
        scene_type: str,
        max_queries: int = 10,
    ) -> list[str]:
        """
        Return up to *max_queries* de-duplicated queries, most specific first.
        """
        subject = (intent.primary_subject or "").strip()
        action = (intent.action or "").strip()
        env = (intent.environment or "").strip()
        mood = (intent.mood or "cinematic").strip()

        if scene_type == "specific":
            raw = self._specific_queries(subject, action, env, intent.must_show)
        elif scene_type == "general":
            raw = self._general_queries(subject, action, env, mood)
        else:  # mixed
            raw = self._mixed_queries(subject, action, env, mood)

        return self._dedupe_and_clean(raw, max_queries)

    # ------------------------------------------------------------------
    # Query templates
    # ------------------------------------------------------------------

    def _specific_queries(
        self,
        subject: str,
        action: str,
        env: str,
        must_show: list[str],
    ) -> list[str]:
        q: list[str] = []

        # Most specific first
        if subject:
            if action and env:
                q.append(f"{subject} {action} {env}")
            if action:
                q.append(f"{subject} {action}")
            if env:
                q.append(f"{subject} {env}")
            q.append(f"{subject} official photo")
            q.append(f"{subject} high resolution")
            q.append(f"{subject} press photo")
            q.append(f"{subject} front view")
            q.append(f"{subject} exterior view")
            q.append(subject)

        # must_show enrichment
        if must_show and subject:
            extra_terms = " ".join(must_show[:2])
            q.append(f"{subject} {extra_terms}")

        return q

    def _general_queries(
        self,
        subject: str,
        action: str,
        env: str,
        mood: str,
    ) -> list[str]:
        q: list[str] = []

        if action and env:
            q.append(f"{action} {env} {mood}")
            q.append(f"{action} {env}")
        if env:
            q.append(f"{env} {mood} cinematic")
            q.append(f"{env} b-roll")
        if action:
            q.append(f"{action} cinematic footage")
        if subject:
            q.append(f"{subject} cinematic")
            q.append(f"{subject} {mood}")
            q.append(subject)

        q.append(f"{mood} b-roll")
        q.append("cinematic footage")

        return q

    def _mixed_queries(
        self,
        subject: str,
        action: str,
        env: str,
        mood: str,
    ) -> list[str]:
        # Subject-specific queries (for Brave images)
        specific = self._specific_queries(subject, action, env, [])
        # Environment/supporting queries (for Pexels video)
        general = self._general_queries(subject, action, env, mood)

        # Interleave: specific first, then alternate
        mixed: list[str] = []
        for s, g in zip(specific[:5], general[:5]):
            mixed.append(s)
            mixed.append(g)
        mixed.extend(specific[5:])
        mixed.extend(general[5:])

        return mixed

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _dedupe_and_clean(self, queries: list[str], limit: int) -> list[str]:
        result: list[str] = []
        for q in queries:
            q = _clean_query(q)
            if not q:
                continue
            key = q.lower()
            if key in self._used:
                continue
            self._used.add(key)
            result.append(q)
            if len(result) >= limit:
                break
        return result


def _clean_query(q: str) -> str:
    """Remove extra whitespace, limit to 12 words."""
    words = re.findall(r"[A-Za-z0-9\-']+", q)
    return " ".join(words[:12]).strip()

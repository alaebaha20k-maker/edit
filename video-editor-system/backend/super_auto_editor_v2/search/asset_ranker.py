from __future__ import annotations

"""
asset_ranker.py
---------------
Rank image and video candidates by RELEVANCE first, quality second.

Old approach: resolution + aspect ratio only → wrong images ranked #1.
New approach:
  - Semantic relevance = exact phrase match + word overlap + must-show terms
  - Must-avoid penalty
  - Quality (resolution + aspect ratio) is secondary (30% weight)
  - Candidates with relevance < MIN_RELEVANCE are filtered out
"""

import re
from difflib import SequenceMatcher

from super_auto_editor_v2.models import ImageCandidate, VideoCandidate, VisualIntent


MIN_IMAGE_RELEVANCE = 0.08   # drop completely irrelevant images
MIN_VIDEO_RELEVANCE = 0.0    # videos use tag scores; keep all and sort

DEFAULT_MUST_AVOID = [
    "cartoon", "illustration", "anime", "drawing", "clipart",
    "watermark", "vector", "icon", "logo", "avatar",
    "1x1", "pixel", "thumbnail", "placeholder",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rank_images(
    candidates: list[ImageCandidate],
    query: str,
    must_show: list[str] | None = None,
    must_avoid: list[str] | None = None,
) -> list[ImageCandidate]:
    """
    Rank images by relevance (70%) then quality (30%).
    Filters out candidates below MIN_IMAGE_RELEVANCE threshold.
    """
    if must_avoid is None:
        must_avoid = DEFAULT_MUST_AVOID
    if must_show is None:
        must_show = []

    scored: list[ImageCandidate] = []
    for c in candidates:
        candidate_text = f"{c.title} {c.source}".strip()
        relevance, matched = _calculate_relevance(
            candidate_text, query, must_show, must_avoid
        )

        quality = _image_quality(c.width, c.height)

        c.score = relevance * 0.70 + quality * 0.30
        c.relevance_score = relevance
        c.matched_terms = matched

        if relevance < MIN_IMAGE_RELEVANCE:
            continue
        scored.append(c)

    return sorted(scored, key=lambda x: x.score, reverse=True)


def rank_videos(
    candidates: list[VideoCandidate],
    query: str,
    visual_intent: VisualIntent | None = None,
) -> list[VideoCandidate]:
    """
    Rank videos by: tag relevance (50%) + duration fit (30%) + resolution (20%).
    """
    must_show = visual_intent.must_show if visual_intent else []
    must_avoid = visual_intent.must_avoid if visual_intent else DEFAULT_MUST_AVOID
    query_words = set(re.findall(r"\w+", query.lower()))

    for c in candidates:
        # Tag relevance
        tag_words = set(c.tags) if c.tags else set()
        tag_overlap = len(query_words & tag_words) / len(query_words) if query_words else 0.0

        # Also check must_show terms in tags
        must_hit = sum(1 for m in must_show if m.lower() in tag_words)
        must_ratio = must_hit / len(must_show) if must_show else 0.0

        relevance = tag_overlap * 0.7 + must_ratio * 0.3

        # Must-avoid penalty in tags
        avoid_hit = sum(1 for a in must_avoid if a.lower() in tag_words)
        relevance = max(0.0, relevance - avoid_hit * 0.15)

        # Duration score: prefer 8-15s clips
        duration = c.duration
        if 8 <= duration <= 15:
            dur_score = 1.0
        elif 5 <= duration <= 20:
            dur_score = 0.6
        else:
            dur_score = 0.2

        # Resolution
        resolution = min(1.0, (c.width * c.height) / (1920 * 1080))
        ratio = _ratio_score(c.width, c.height)
        quality = resolution * 0.6 + ratio * 0.4

        c.relevance_score = relevance
        c.score = relevance * 0.50 + dur_score * 0.30 + quality * 0.20

    return sorted(candidates, key=lambda x: x.score, reverse=True)


# ---------------------------------------------------------------------------
# Relevance calculation
# ---------------------------------------------------------------------------

def calculate_relevance(
    candidate_text: str,
    query: str,
    must_show: list[str],
    must_avoid: list[str],
) -> tuple[float, list[str]]:
    """Public wrapper for use in searchers."""
    return _calculate_relevance(candidate_text, query, must_show, must_avoid)


def _calculate_relevance(
    candidate_text: str,
    query: str,
    must_show: list[str],
    must_avoid: list[str],
) -> tuple[float, list[str]]:
    text = candidate_text.lower()
    query_lower = query.lower()
    query_words = set(re.findall(r"\w+", query_lower))

    score = 0.0
    matched: list[str] = []

    # 1. Exact phrase match (strongest signal)
    if query_lower and query_lower in text:
        score += 0.40
        matched.append(query)

    # 2. Word overlap
    text_words = set(re.findall(r"\w+", text))
    if query_words:
        overlap = query_words & text_words
        overlap_ratio = len(overlap) / len(query_words)
        score += overlap_ratio * 0.30
        matched.extend(list(overlap))

    # 3. Must-show terms
    if must_show:
        hits = sum(1 for t in must_show if t.lower() in text)
        score += (hits / len(must_show)) * 0.20
        matched.extend([t for t in must_show if t.lower() in text])

    # 4. Fuzzy similarity (handles typos, plurals)
    if query_lower and len(text) > 0:
        snippet = text[: min(len(text), 200)]
        similarity = SequenceMatcher(None, query_lower, snippet).ratio()
        score += similarity * 0.10

    # 5. Must-avoid penalty
    for term in must_avoid:
        if term.lower() in text:
            score -= 0.12

    return max(0.0, min(1.0, score)), list(dict.fromkeys(matched))


# ---------------------------------------------------------------------------
# Image quality helpers
# ---------------------------------------------------------------------------

def _image_quality(width: int, height: int) -> float:
    resolution = min(1.0, (width * height) / (1920 * 1080))
    ratio = _ratio_score(width, height)
    return resolution * 0.60 + ratio * 0.40


def _ratio_score(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    ratio = width / height
    return max(0.0, 1.0 - abs((16 / 9) - ratio))


# ---------------------------------------------------------------------------
# Pre-download validation
# ---------------------------------------------------------------------------

def validate_image_candidate(
    candidate: ImageCandidate,
    visual_intent: VisualIntent | None = None,
) -> bool:
    """
    Return True if the candidate is worth downloading.
    Quick filter to avoid wasting bandwidth on obviously wrong images.
    """
    if candidate.relevance_score < MIN_IMAGE_RELEVANCE:
        return False

    if visual_intent is None:
        return True

    title_lower = (candidate.title or "").lower()

    # Must-avoid check
    for term in (visual_intent.must_avoid or DEFAULT_MUST_AVOID):
        if term.lower() in title_lower:
            return False

    return True

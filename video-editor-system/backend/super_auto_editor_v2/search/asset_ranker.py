from __future__ import annotations

from super_auto_editor_v2.models import ImageCandidate, VideoCandidate


def _ratio_score(width: int, height: int) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    ratio = width / height
    return max(0.0, 1.0 - abs((16 / 9) - ratio))


def rank_images(candidates: list[ImageCandidate], query: str) -> list[ImageCandidate]:
    q = query.lower()
    for c in candidates:
        title = (c.title or "").lower()
        exact = 1.0 if q and q in title else 0.0
        resolution = min(1.0, (c.width * c.height) / (1920 * 1080))
        ratio = _ratio_score(c.width, c.height)
        c.score = exact * 0.5 + resolution * 0.3 + ratio * 0.2
    return sorted(candidates, key=lambda x: x.score, reverse=True)


def rank_videos(candidates: list[VideoCandidate], query: str) -> list[VideoCandidate]:
    del query
    for c in candidates:
        resolution = min(1.0, (c.width * c.height) / (1920 * 1080))
        ratio = _ratio_score(c.width, c.height)
        dur_penalty = 0.0 if 5 <= c.duration <= 20 else 0.2
        c.score = resolution * 0.6 + ratio * 0.4 - dur_penalty
    return sorted(candidates, key=lambda x: x.score, reverse=True)

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
        # Prefer 10-15s clips for general scenes while allowing 5-20s fallback.
        if 10 <= c.duration <= 15:
            dur_score = 1.0
        elif 5 <= c.duration <= 20:
            dur_score = 0.6
        else:
            dur_score = 0.1
        c.score = resolution * 0.45 + ratio * 0.35 + dur_score * 0.20
    return sorted(candidates, key=lambda x: x.score, reverse=True)

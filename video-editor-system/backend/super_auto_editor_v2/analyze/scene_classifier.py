from __future__ import annotations

import re

from super_auto_editor_v2.models import SceneType


GENERIC_TERMS = {
    "success", "travel", "nature", "technology", "forest", "business", "city",
    "social media", "ai", "money", "meeting", "people", "cars", "space",
    "walking", "street", "alone", "sad", "hope", "emotional", "cinematic", "room",
}
STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "then", "when", "where",
    "your", "their", "have", "will", "about", "video", "scene", "show", "shows", "a", "an",
}


def classify_scene_type(text: str, entities: list[str]) -> SceneType:
    lower = text.lower()
    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if w]
    content_words = [w for w in words if w.lower() not in STOP_WORDS]

    # Strong signals for specific/entity-driven scenes.
    if re.search(r"\b[A-Za-z]+[- ]?\d{1,4}\b", text):  # e.g. iPhone 15, RTX-4090
        return "specific"
    if entities:
        return "specific"

    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    flattened = [q1 or q2 for q1, q2 in quoted if (q1 or q2)]
    if any(len(item.split()) >= 2 for item in flattened):
        return "specific"

    title_case_count = sum(1 for w in words if w[:1].isupper())
    if title_case_count >= 2:
        return "specific"

    # If chunk is short and focused, bias to specific (prevents over-routing to Pexels).
    if 1 <= len(content_words) <= 5 and not any(term in lower for term in GENERIC_TERMS):
        return "specific"

    if any(term in lower for term in GENERIC_TERMS) and title_case_count == 0:
        return "general"

    # Action/emotion sentences are usually conceptual B-roll -> general.
    if any(v in lower for v in ("feels", "walking", "walks", "finds", "hope", "lost")) and title_case_count == 0:
        return "general"

    return "general"

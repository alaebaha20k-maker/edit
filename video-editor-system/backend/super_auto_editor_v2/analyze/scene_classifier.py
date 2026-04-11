from __future__ import annotations

import re

from super_auto_editor_v2.models import SceneType


GENERIC_TERMS = {
    "success", "travel", "nature", "technology", "forest", "business", "city",
    "social media", "ai", "money", "meeting", "people", "cars", "space",
}


def classify_scene_type(text: str, entities: list[str]) -> SceneType:
    lower = text.lower()
    if entities:
        return "specific"

    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    flattened = [q1 or q2 for q1, q2 in quoted if (q1 or q2)]
    if any(len(item.split()) >= 2 for item in flattened):
        return "specific"

    if any(term in lower for term in GENERIC_TERMS):
        return "general"

    words = [w for w in re.findall(r"[A-Za-z0-9]+", text) if len(w) > 2]
    title_case_count = sum(1 for w in words if w[:1].isupper())
    if title_case_count >= 2:
        return "specific"
    return "general"

from __future__ import annotations

import json
import re
from typing import Any

from super_auto_editor_v2.analyze.scene_classifier import classify_scene_type
from super_auto_editor_v2.models import MediaSource, SceneAnalysis, TimelineBlock

try:
    import google.generativeai as genai
except Exception:  # optional dependency at runtime
    genai = None

# ---- filler words stripped before building image-search queries ----
_FILLER = {
    "the", "a", "an", "and", "or", "but", "for", "with", "this", "that",
    "from", "into", "then", "when", "where", "your", "their", "have", "will",
    "about", "video", "scene", "show", "shows", "also", "very", "just", "its",
    "it", "they", "we", "you", "he", "she", "was", "were", "are", "is", "in",
    "on", "to", "of", "at", "by", "as", "so", "if", "all", "can", "has",
    "been", "do", "does", "did", "our", "be", "not", "no", "new", "how",
}

# ---- topic-category hints used to pick relevant visual modifiers ----
_CAR_HINTS = {"car", "vehicle", "sedan", "suv", "truck", "coupe", "hatchback",
              "ford", "toyota", "bmw", "audi", "mercedes", "tesla", "honda",
              "chevrolet", "hyundai", "kia", "nissan", "volkswagen", "vw",
              "driving", "engine", "horsepower", "mph", "torque"}
_TECH_HINTS = {"phone", "laptop", "tablet", "iphone", "ipad", "android",
               "samsung", "pixel", "macbook", "gpu", "cpu", "rtx", "chip",
               "processor", "gadget", "device", "smartphone", "watch",
               "earbuds", "headphones", "camera", "console", "playstation",
               "xbox", "nintendo", "software", "app"}
_PERSON_HINTS = {"ceo", "founder", "actor", "singer", "president", "player",
                 "athlete", "coach", "director", "artist", "musician",
                 "influencer", "youtuber", "celebrity"}
_FOOD_HINTS = {"recipe", "food", "dish", "meal", "restaurant", "cook",
               "cooking", "ingredient", "pizza", "burger", "sushi", "coffee",
               "chocolate", "cake"}
_PLACE_HINTS = {"city", "country", "island", "mountain", "beach", "lake",
                "park", "museum", "tower", "bridge", "hotel", "resort",
                "airport", "stadium"}


def _detect_category(text_lower: str, entities: list[str]) -> str:
    """Return a rough topic category from the script text."""
    combined = text_lower + " " + " ".join(e.lower() for e in entities)
    tokens = set(combined.split())
    if tokens & _CAR_HINTS:
        return "car"
    if tokens & _TECH_HINTS:
        return "tech"
    if tokens & _PERSON_HINTS:
        return "person"
    if tokens & _FOOD_HINTS:
        return "food"
    if tokens & _PLACE_HINTS:
        return "place"
    return "generic"


def _clean_subject(text: str) -> str:
    """Extract the meaningful subject from script text, stripping filler."""
    words = text.split()
    clean = [w for w in words if w.lower() not in _FILLER]
    return " ".join(clean[:6]).strip()


class ScriptAnalyzer:
    def __init__(self, gemini_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        if gemini_api_key and genai:
            genai.configure(api_key=gemini_api_key)

    def analyze(self, block: TimelineBlock) -> SceneAnalysis:
        data = self._analyze_with_gemini(block.script_text) if self.gemini_api_key else None
        if not data:
            data = self._heuristic_analyze(block.script_text)

        scene_type = classify_scene_type(block.script_text, data.get("named_entities", []))
        source: MediaSource = "brave_images" if scene_type == "specific" else "pexels_video"
        queries = self._build_queries(
            text=block.script_text,
            scene_type=scene_type,
            keywords=data.get("keywords", []),
            entities=data.get("named_entities", []),
        )
        return SceneAnalysis(
            keywords=data.get("keywords", []),
            named_entities=data.get("named_entities", []),
            scene_type=scene_type,
            source=source,
            search_queries=queries,
        )

    # ------------------------------------------------------------------ #
    #  Gemini extraction (richer prompt → better keywords + entities)     #
    # ------------------------------------------------------------------ #

    def _analyze_with_gemini(self, text: str) -> dict[str, Any] | None:
        if not genai:
            return None
        prompt = (
            "You are analysing a short video script excerpt for an automated "
            "image/video search pipeline. Return ONLY valid JSON.\n\n"
            "Keys:\n"
            '  "keywords"       – 3-6 visually descriptive words (nouns/adjectives '
            "that would match good stock images). Remove filler.\n"
            '  "named_entities" – proper nouns: product names, brand names, '
            "person names, place names. Keep model numbers (e.g. iPhone 15, RTX 4090).\n"
            '  "visual_subject" – the single best short phrase (2-5 words) that '
            "describes what an image result SHOULD look like for this text.\n\n"
            f"Text:\n{text}"
        )
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None
            return json.loads(raw[start : end + 1])
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Heuristic fallback                                                 #
    # ------------------------------------------------------------------ #

    def _heuristic_analyze(self, text: str) -> dict[str, Any]:
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", text)
        keywords = [t for t in tokens if t.lower() not in _FILLER and len(t) > 2][:8]
        named_entities: list[str] = []
        for i, token in enumerate(tokens):
            if token[:1].isupper() and token.lower() not in _FILLER:
                if i + 1 < len(tokens) and tokens[i + 1][:1].isupper():
                    named_entities.append(f"{token} {tokens[i + 1]}")
                else:
                    named_entities.append(token)
        dedup_entities = list(dict.fromkeys(named_entities))[:4]
        return {"keywords": keywords, "named_entities": dedup_entities}

    # ------------------------------------------------------------------ #
    #  Smart query builder — category-aware visual search queries         #
    # ------------------------------------------------------------------ #

    def _build_queries(
        self,
        text: str,
        scene_type: str,
        keywords: list[str],
        entities: list[str],
    ) -> list[str]:
        banned = {"it", "this", "that", "they", "we", "you", "he", "she", ""}

        if scene_type == "specific":
            return self._build_specific_queries(text, keywords, entities, banned)
        return self._build_general_queries(text, keywords, entities, banned)

    # -- SPECIFIC scenes → Brave Images (5-7 targeted queries) ---------- #

    def _build_specific_queries(
        self, text: str, keywords: list[str], entities: list[str], banned: set[str],
    ) -> list[str]:
        # Core subject: prefer named entity, then cleaned script, then keywords.
        subject = (
            entities[0]
            if entities
            else _clean_subject(text) or " ".join(keywords[:3])
        )
        category = _detect_category(text.lower(), entities)

        # Category-aware visual modifiers.
        if category == "car":
            modifiers = [
                "photo", "front view", "exterior", "on road",
                "side profile", "close up", "official press photo",
            ]
        elif category == "tech":
            modifiers = [
                "product photo", "official", "hands on", "close up",
                "unboxing", "studio shot", "HD",
            ]
        elif category == "person":
            modifiers = [
                "portrait", "photo", "speaking", "press photo",
                "high resolution", "official", "HD",
            ]
        elif category == "food":
            modifiers = [
                "photo", "close up", "plated", "top view",
                "restaurant", "homemade", "HD",
            ]
        elif category == "place":
            modifiers = [
                "photo", "aerial view", "panorama", "landmark",
                "travel", "scenic", "HD",
            ]
        else:
            modifiers = [
                "photo", "high quality", "close up", "HD",
                "official image", "detailed", "professional",
            ]

        variants: list[str] = [subject]
        for mod in modifiers:
            variants.append(f"{subject} {mod}")
            if len(variants) >= 7:
                break

        return [q.strip() for q in variants if q.strip().lower() not in banned][:7]

    # -- GENERAL scenes → Pexels Videos (3-5 mood/aesthetic queries) ---- #

    def _build_general_queries(
        self, text: str, keywords: list[str], entities: list[str], banned: set[str],
    ) -> list[str]:
        # Build a compact topic phrase from content words.
        topic = _clean_subject(text) if text else ""
        if not topic:
            topic = " ".join(keywords[:3])
        # Shorten to avoid overly long Pexels queries (API works best ≤ 4 words).
        topic_words = topic.split()[:4]
        short_topic = " ".join(topic_words)

        category = _detect_category(text.lower(), entities)

        # Pick aesthetic modifiers that complement the topic category.
        if category == "car":
            extras = ["driving cinematic", "highway aerial", "car motion"]
        elif category == "tech":
            extras = ["technology modern", "digital abstract", "futuristic"]
        elif category == "person":
            extras = ["people lifestyle", "crowd cinematic", "portrait"]
        elif category == "food":
            extras = ["food preparation", "cooking cinematic", "ingredients"]
        elif category == "place":
            extras = ["aerial landscape", "travel cinematic", "scenic nature"]
        else:
            extras = ["cinematic", "aerial", "abstract motion"]

        variants: list[str] = [short_topic]
        for extra in extras:
            variants.append(f"{short_topic} {extra}")
        # Deduplicate and trim.
        seen: set[str] = set()
        out: list[str] = []
        for q in variants:
            q = q.strip()
            low = q.lower()
            if low not in seen and low not in banned:
                seen.add(low)
                out.append(q)
        return out[:5]

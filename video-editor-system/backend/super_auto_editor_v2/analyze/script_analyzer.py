from __future__ import annotations

import json
import re
from typing import Any

from super_auto_editor_v2.analyze.global_topic_extractor import GlobalTopicExtractor
from super_auto_editor_v2.analyze.scene_classifier import classify_scene_type
from super_auto_editor_v2.analyze.visual_intent_extractor import (
    extract_visual_intent,
    merge_gemini_intent,
)
from super_auto_editor_v2.models import MediaSource, SceneAnalysis, TimelineBlock, VisualIntent

try:
    import google.generativeai as genai
except Exception:  # optional dependency at runtime
    genai = None

# ---------------------------------------------------------------------------
# Improved Gemini prompt for precise visual intent extraction
# ---------------------------------------------------------------------------

_GEMINI_PROMPT_TEMPLATE = """You are a professional video editor deciding what visuals to show for each script segment.

For the text below, identify exactly what should appear on screen.

Return ONLY valid JSON with these keys:

{{
  "primary_subject": "The EXACT thing that MUST appear on screen. For products include brand+model+year. For people include name+role. For places include specific name.",
  "subject_type": "One of: product | person | place | concept | action",
  "visual_action": "What should be happening: e.g. 'driving on highway', 'front view', 'close-up', 'aerial view', 'interior walkthrough'",
  "environment": "Where the visual takes place: e.g. 'highway', 'showroom', 'office', 'outdoors', 'studio'",
  "mood": "Visual mood: e.g. 'cinematic', 'bright', 'dramatic', 'professional', 'energetic'",
  "must_show": ["list", "of", "things", "that", "MUST", "appear"],
  "must_avoid": ["cartoon", "illustration", "watermark", "low quality"],
  "search_queries": [
    "MOST SPECIFIC query first - include brand+model+year+action",
    "Second most specific - brand+model+context",
    "Moderate specificity - brand+model",
    "Broader fallback - category+action",
    "Generic fallback - just the category"
  ],
  "scene_type": "specific | general | mixed",
  "keywords": ["main", "keywords"],
  "named_entities": ["Named Entity One", "Named Entity Two"]
}}

Rules:
- For "Ford Focus 2024 driving on highway": primary_subject="Ford Focus 2024", subject_type="product", search_queries=["Ford Focus 2024 driving highway", "Ford Focus 2024 exterior", "Ford Focus 2024", "Ford car highway", "car driving highway"]
- For "Elon Musk announced the product": primary_subject="Elon Musk", subject_type="person"
- For "success requires hard work": subject_type="concept", scene_type="general"
- search_queries[0] must be the MOST SPECIFIC - never a single generic word
- must_avoid always include: cartoon, illustration, anime, drawing, watermark

TEXT TO ANALYZE:
{text}

Return JSON only, no markdown, no explanation."""


class ScriptAnalyzer:
    def __init__(self, gemini_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        self.main_subject = ""
        self.global_topic_extractor = GlobalTopicExtractor(gemini_api_key)
        self.global_topic_info: dict = {}
        if gemini_api_key and genai:
            genai.configure(api_key=gemini_api_key)

    def set_context(self, full_script: str) -> None:
        """Extract global topic and anchor subject from full script."""
        # Extract global topic (CRITICAL FIX: used as fallback for stop-word subjects)
        self.global_topic_info = self.global_topic_extractor.extract(full_script)
        global_topic = self.global_topic_info.get("main_topic", "")
        context_phrases = self.global_topic_info.get("context_phrases", [])

        # Look for brand/product names first
        product_match = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z0-9]+)*(?:\s+\d{4})?)\b",
            full_script,
        )
        if product_match:
            self.main_subject = product_match.group(0).strip()
        else:
            # Fallback: use global topic or first 3 tokens
            self.main_subject = global_topic or " ".join(
                re.findall(r"[A-Za-z0-9\-]+", full_script)[:3]
            ).strip()

    def analyze(self, block: TimelineBlock) -> SceneAnalysis:
        # Step 1: heuristic visual intent (always runs - fast, no API)
        global_topic = self.global_topic_info.get("main_topic", "")
        heuristic_intent = extract_visual_intent(block.script_text, global_topic=global_topic)

        # Step 2: Gemini enrichment (if available)
        gemini_data = self._analyze_with_gemini(block.script_text) if self.gemini_api_key else None

        if gemini_data:
            visual_intent = merge_gemini_intent(heuristic_intent, gemini_data)
        else:
            visual_intent = heuristic_intent

        # Step 3: classify scene type
        # IMPORTANT: Gemini's scene_type is NOT trusted for Brave routing.
        # Only the classifier (which checks KNOWN_BRANDS) decides if Brave is used.
        # This prevents Brave returning anime/t-shirts for generic nouns.
        scene_type = classify_scene_type(
            block.script_text,
            visual_intent.must_show + [visual_intent.primary_subject],
            subject_type=visual_intent.subject_type,
        )

        # Step 4: determine media source
        source: MediaSource = _scene_type_to_source(scene_type)

        # Step 5: build final queries
        queries = self._resolve_queries(visual_intent, scene_type, gemini_data)

        # Step 6: extract keywords / entities for downstream consumers
        keywords = (
            [str(k) for k in (gemini_data.get("keywords") or [])]
            if gemini_data
            else _heuristic_keywords(block.script_text)
        )
        named_entities = (
            [str(e) for e in (gemini_data.get("named_entities") or [])]
            if gemini_data
            else [visual_intent.primary_subject] if visual_intent.primary_subject else []
        )

        return SceneAnalysis(
            keywords=keywords[:8],
            named_entities=named_entities[:4],
            scene_type=scene_type,
            source=source,
            search_queries=queries,
            visual_intent=visual_intent,
        )

    # ------------------------------------------------------------------
    # Gemini call
    # ------------------------------------------------------------------

    def _analyze_with_gemini(self, text: str) -> dict[str, Any] | None:
        if not genai:
            return None
        prompt = _GEMINI_PROMPT_TEMPLATE.format(text=text)
        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None
            parsed = json.loads(raw[start : end + 1])
            # Validate scene_type
            if parsed.get("scene_type") not in ("specific", "general", "mixed"):
                parsed["scene_type"] = None
            return parsed
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Query resolution
    # ------------------------------------------------------------------

    def _resolve_queries(
        self,
        intent: VisualIntent,
        scene_type: str,
        gemini_data: dict | None,
    ) -> list[str]:
        # Priority 1: Gemini-provided queries (most precise)
        if gemini_data:
            raw = gemini_data.get("search_queries") or []
            if isinstance(raw, list) and raw:
                queries = [str(q).strip() for q in raw if str(q).strip()][:10]
                if queries:
                    return queries

        # Priority 2: VisualIntent queries from heuristic extractor
        if intent.search_queries:
            return intent.search_queries[:10]

        # Priority 3: Build from intent fields with global topic enrichment
        subject = intent.primary_subject or "subject"
        action = intent.action or ""
        env = intent.environment or ""
        global_topic = self.global_topic_info.get("main_topic", "")
        context_phrases = self.global_topic_info.get("context_phrases", [])

        if scene_type in ("specific", "mixed"):
            variants = [
                # CRITICAL FIX: Always include global topic first for context
                f"{global_topic} {subject}".strip() if global_topic and subject != global_topic else subject,
                f"{subject} {action} {env}".strip(),
                f"{subject} official photo",
                f"{subject} high resolution",
                f"{subject} {action}".strip() if action else f"{subject} front view",
                f"{subject} {env}".strip() if env else f"{subject} exterior",
                subject,
            ]
        else:
            mood = intent.mood or "cinematic"
            variants = [
                # For general scenes, still include global context
                f"{global_topic} {action} {env} {mood}".strip() if global_topic else f"{action} {env} {mood}".strip(),
                f"{action} {env} {mood}".strip(),
                f"{env} {mood} b-roll".strip() if env else f"{mood} b-roll",
                f"{subject} cinematic",
                f"{subject}",
            ]

        # Enrich with main_subject context if needed
        enriched = []
        for q in variants:
            q = q.strip()
            if not q:
                continue
            enriched.append(q)

        # Add context phrases if available
        if context_phrases:
            for phrase in context_phrases[:2]:
                enriched.append(f"{phrase} {subject}".strip() if subject else phrase)

        # Dedupe
        seen: set[str] = set()
        result = []
        for q in enriched:
            if q.lower() not in seen:
                seen.add(q.lower())
                result.append(q)

        return [q for q in result if len(q.split()) <= 12][:10]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scene_type_to_source(scene_type: str) -> MediaSource:
    if scene_type == "specific":
        return "brave_images"
    if scene_type == "mixed":
        return "mixed"
    return "pexels_video"


def _heuristic_keywords(text: str) -> list[str]:
    stop_words = {
        "the", "and", "for", "with", "this", "that", "from", "into", "then",
        "when", "where", "your", "their", "have", "will", "about", "video",
        "a", "an", "in", "on", "at", "to", "of", "is", "are", "was",
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", text)
    return [t for t in tokens if t.lower() not in stop_words and len(t) > 2][:8]

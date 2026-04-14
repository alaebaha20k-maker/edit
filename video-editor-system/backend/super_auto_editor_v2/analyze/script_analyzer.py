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
from super_auto_editor_v2.models import (
    MediaPlan,
    MediaSource,
    SceneAnalysis,
    TimelineBlock,
    VisualIntent,
)

try:
    import google.generativeai as genai
except Exception:
    genai = None


# ---------------------------------------------------------------------------
# Batch keyword generation prompt (ONE Gemini call for ALL media segments)
# ---------------------------------------------------------------------------

_BATCH_KEYWORDS_PROMPT = """\
You are a professional video editor choosing B-roll media keywords for a full video script.

VIDEO TOPIC: {global_topic}
SCRIPT PREVIEW: {script_preview}

Below are {n_segments} MEDIA SEGMENTS — each one is a 15-second B-roll window.
Generate one media plan per segment. Return ONLY a JSON array — no markdown, no explanation.

[
  {{
    "idx": 0,
    "primary_keyword": "most specific photographable noun phrase",
    "fallback_keyword": "slightly broader fallback if primary returns nothing",
    "api_choice": "SERPER",
    "serper_keyword": null,
    "pexels_keyword": null
  }}
]

API CHOICE RULES:
- SERPER  → Google Images. Use for NAMED brands, models, people, specific cities.
            Examples: "Ford F-150 2024 red exterior", "Elon Musk speaking stage",
                      "New York City skyline night", "iPhone 15 Pro unboxing"
- PEXELS  → Stock video 15-20s. Use for generic actions, environments, landscapes.
            Examples: "highway driving cinematic sunset", "busy office workers meeting",
                      "mountain forest aerial drone", "construction workers building"
- MERGE   → Serper image (specific subject) + Pexels video (environment/action).
            Set serper_keyword = named subject, pexels_keyword = environment.
            Example: serper="Ford F-150 exterior red", pexels="highway driving truck"

KEYWORD RULES (strictly enforced):
- Physical and photographable ONLY — NO abstract concepts
- Include brand/model when mentioned: NEVER "truck" alone if "Ford F-150" was said
- Short noun phrases with descriptive adjectives (stock-site language)
- No articles (a, the) unless critical
- No repeated keywords across all segments — each must be unique
- NEVER use: innovation, future, AI, digital, concept, data, network, smart, cloud, cyber
- NEVER use keywords that produce merch: do not add "shirt", "poster", "art" etc.
- Emotional direction must match script tone

MEDIA SEGMENTS (the avatar script text shown during each B-roll window):
{segments_json}

Return the JSON array only. One entry per segment, idx matching the order above."""


# ---------------------------------------------------------------------------
# Per-segment Gemini enrichment prompt (used for analyze() fallback)
# ---------------------------------------------------------------------------

_GEMINI_PROMPT_TEMPLATE = """\
You are a professional video editor deciding what visuals to show for a script segment.

Return ONLY valid JSON with these keys:

{{
  "primary_subject": "The EXACT thing that MUST appear on screen.",
  "subject_type": "product | person | place | concept | action",
  "visual_action": "What should be happening: e.g. 'driving on highway'",
  "environment": "Where the visual takes place",
  "mood": "Visual mood: cinematic | bright | dramatic | professional",
  "must_show": ["list", "of", "required", "elements"],
  "must_avoid": ["cartoon", "illustration", "watermark", "low quality"],
  "search_queries": [
    "MOST SPECIFIC query first",
    "Second specific",
    "Moderate",
    "Broader fallback",
    "Generic fallback"
  ],
  "scene_type": "specific | general | mixed",
  "keywords": ["main", "keywords"],
  "named_entities": ["Named Entity One"]
}}

TEXT TO ANALYZE:
{text}

Return JSON only."""


class ScriptAnalyzer:
    def __init__(self, gemini_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        self.main_subject = ""
        self.global_topic_extractor = GlobalTopicExtractor(gemini_api_key)
        self.global_topic_info: dict = {}
        self._full_script: str = ""
        if gemini_api_key and genai:
            genai.configure(api_key=gemini_api_key)

    def set_context(self, full_script: str) -> None:
        """Extract global topic from full script (run once before analyzing blocks)."""
        self._full_script = full_script
        self.global_topic_info = self.global_topic_extractor.extract(full_script)
        global_topic = self.global_topic_info.get("main_topic", "")

        product_match = re.search(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z0-9]+)*(?:\s+\d{4})?)\b",
            full_script,
        )
        if product_match:
            self.main_subject = product_match.group(0).strip()
        else:
            self.main_subject = global_topic or " ".join(
                re.findall(r"[A-Za-z0-9\-]+", full_script)[:3]
            ).strip()

    # ------------------------------------------------------------------
    # Batch media plan generation (STEP 3 in the pipeline)
    # ONE Gemini call for ALL media segments → fast + full context
    # ------------------------------------------------------------------

    def generate_media_plans(
        self, media_blocks: list[tuple[int, TimelineBlock]]
    ) -> dict[int, MediaPlan]:
        """
        Generate MediaPlan for every media block in one Gemini API call.
        Falls back to heuristic plans when Gemini is unavailable.

        Returns {block_index: MediaPlan}
        """
        if not media_blocks:
            return {}

        if not self.gemini_api_key or not genai:
            return self._heuristic_media_plans(media_blocks)

        return self._gemini_batch_media_plans(media_blocks)

    def _gemini_batch_media_plans(
        self, media_blocks: list[tuple[int, TimelineBlock]]
    ) -> dict[int, MediaPlan]:
        global_topic = self.global_topic_info.get("main_topic", "")
        script_preview = self._full_script[:600].replace("\n", " ")

        # Build segments JSON — what the avatar says during each media window
        segments = [
            {"idx": i, "segment_text": block.script_text[:300]}
            for i, (_, block) in enumerate(media_blocks)
        ]
        segments_json = json.dumps(segments, indent=2)

        prompt = _BATCH_KEYWORDS_PROMPT.format(
            global_topic=global_topic or "general topic",
            script_preview=script_preview,
            n_segments=len(media_blocks),
            segments_json=segments_json,
        )

        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            # Extract JSON array
            start = raw.find("[")
            end = raw.rfind("]")
            if start == -1 or end == -1:
                raise ValueError("No JSON array in Gemini response")
            parsed: list[dict] = json.loads(raw[start: end + 1])
        except Exception as exc:
            print(f"[ScriptAnalyzer] Gemini batch failed ({exc}), using heuristics")
            return self._heuristic_media_plans(media_blocks)

        plans: dict[int, MediaPlan] = {}
        for entry in parsed:
            segment_pos = int(entry.get("idx", 0))
            if segment_pos >= len(media_blocks):
                continue
            block_idx = media_blocks[segment_pos][0]

            api_choice = str(entry.get("api_choice") or "PEXELS").upper()
            if api_choice not in ("SERPER", "PEXELS", "MERGE"):
                api_choice = "PEXELS"

            plans[block_idx] = MediaPlan(
                primary_keyword=str(entry.get("primary_keyword") or "").strip(),
                fallback_keyword=str(entry.get("fallback_keyword") or "").strip(),
                api_choice=api_choice,
                serper_keyword=str(entry.get("serper_keyword") or "").strip(),
                pexels_keyword=str(entry.get("pexels_keyword") or "").strip(),
            )

        # Fill any missing entries with heuristics
        for block_idx, block in media_blocks:
            if block_idx not in plans:
                plans[block_idx] = self._heuristic_plan_for(block)

        return plans

    def _heuristic_media_plans(
        self, media_blocks: list[tuple[int, TimelineBlock]]
    ) -> dict[int, MediaPlan]:
        return {
            block_idx: self._heuristic_plan_for(block)
            for block_idx, block in media_blocks
        }

    def _heuristic_plan_for(self, block: TimelineBlock) -> MediaPlan:
        """Fast heuristic media plan when Gemini is unavailable."""
        global_topic = self.global_topic_info.get("main_topic", "")
        intent = extract_visual_intent(block.script_text, global_topic=global_topic)

        subject = intent.primary_subject or global_topic or "cinematic"
        action = intent.action or ""
        env = intent.environment or ""

        primary = f"{subject} {action}".strip() if action else subject
        fallback = f"{subject} {env}".strip() if env else f"{subject} cinematic"

        # Decide API: Serper only if subject looks like a named brand
        from super_auto_editor_v2.analyze.scene_classifier import (
            KNOWN_BRANDS,
            _has_known_brand,
        )
        use_serper = _has_known_brand(block.script_text.lower())

        return MediaPlan(
            primary_keyword=primary,
            fallback_keyword=fallback,
            api_choice="SERPER" if use_serper else "PEXELS",
        )

    # ------------------------------------------------------------------
    # Per-block analysis (used for SceneAnalysis metadata / Gemini fallback)
    # ------------------------------------------------------------------

    def analyze(self, block: TimelineBlock) -> SceneAnalysis:
        global_topic = self.global_topic_info.get("main_topic", "")
        heuristic_intent = extract_visual_intent(block.script_text, global_topic=global_topic)

        gemini_data = self._analyze_with_gemini(block.script_text) if self.gemini_api_key else None

        if gemini_data:
            visual_intent = merge_gemini_intent(heuristic_intent, gemini_data)
        else:
            visual_intent = heuristic_intent

        # Scene type: ONLY based on brand detection (Gemini not trusted for routing)
        scene_type = classify_scene_type(
            block.script_text,
            visual_intent.must_show + [visual_intent.primary_subject],
            subject_type=visual_intent.subject_type,
        )
        source: MediaSource = _scene_type_to_source(scene_type)
        queries = self._resolve_queries(visual_intent, scene_type, gemini_data)

        keywords = (
            [str(k) for k in (gemini_data.get("keywords") or [])]
            if gemini_data
            else _heuristic_keywords(block.script_text)
        )
        named_entities = (
            [str(e) for e in (gemini_data.get("named_entities") or [])]
            if gemini_data
            else ([visual_intent.primary_subject] if visual_intent.primary_subject else [])
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
    # Gemini per-block call (for SceneAnalysis metadata)
    # ------------------------------------------------------------------

    def _analyze_with_gemini(self, text: str) -> dict[str, Any] | None:
        if not genai:
            return None
        prompt = _GEMINI_PROMPT_TEMPLATE.format(text=text)
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None
            parsed = json.loads(raw[start: end + 1])
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
        if gemini_data:
            raw = gemini_data.get("search_queries") or []
            if isinstance(raw, list) and raw:
                queries = [str(q).strip() for q in raw if str(q).strip()][:10]
                if queries:
                    return queries

        if intent.search_queries:
            return intent.search_queries[:10]

        subject = intent.primary_subject or "subject"
        action = intent.action or ""
        env = intent.environment or ""
        global_topic = self.global_topic_info.get("main_topic", "")

        if scene_type in ("specific", "mixed"):
            variants = [
                f"{global_topic} {subject}".strip() if global_topic and subject != global_topic else subject,
                f"{subject} {action} {env}".strip(),
                f"{subject} official photo",
                f"{subject} high resolution",
                subject,
            ]
        else:
            mood = intent.mood or "cinematic"
            variants = [
                f"{global_topic} {action} {env} {mood}".strip() if global_topic else f"{action} {env} {mood}".strip(),
                f"{action} {env} {mood}".strip(),
                f"{env} {mood} b-roll".strip() if env else f"{mood} b-roll",
                subject,
            ]

        seen: set[str] = set()
        result = []
        for q in variants:
            q = q.strip()
            if q and q.lower() not in seen:
                seen.add(q.lower())
                result.append(q)

        return [q for q in result if len(q.split()) <= 12][:10]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _scene_type_to_source(scene_type: str) -> MediaSource:
    if scene_type == "specific":
        return "brave_images"   # label kept; actually routed to Serper
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

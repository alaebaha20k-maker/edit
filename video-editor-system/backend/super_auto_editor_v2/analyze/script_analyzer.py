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
You are a professional video editor sourcing B-roll footage for a YouTube video.
For each 15-second B-roll window, generate highly specific stock media search queries.

VIDEO TOPIC: {global_topic}
KEY VISUAL ELEMENTS: {key_visuals}
CONTEXT PHRASES: {context_phrases}
SCRIPT PREVIEW: {script_preview}

── THINKING PROCESS (apply internally to each segment) ───────────────────────
Step 1 — VISUALIZE: Describe the exact image/video frame a camera would show.
Step 2 — GENERATE: Turn that visual description into stock-site search queries.
──────────────────────────────────────────────────────────────────────────────

QUERY RULES (strictly enforced):
✅ Every query MUST be 5+ words — no single keywords, no 2-3 word phrases
✅ Format: [subject] + [action] + [setting] + [mood/style]
✅ Concrete and photographable ONLY
✅ Replace abstract/emotional concepts with visible actions:
   • "success"    → "entrepreneur smiling signing deal at office desk"
   • "innovation" → "engineer testing new prototype on laboratory bench"
   • "motivation" → "athlete sprinting on track at sunrise golden light"
   • "growth"     → "business chart rising on laptop screen close-up"
   • "future"     → "modern city skyline aerial view blue hour"
   • "happiness"  → "family laughing together in sunny backyard"
✅ Include brand/model name when the script explicitly mentions it
✅ Use stock-site descriptors: cinematic, aerial, close-up, slow motion, 4K, golden hour
✅ Each segment must have a UNIQUE query — no duplicates across the video

❌ NEVER use abstract single words: innovation, future, AI, digital, concept,
   data, network, smart, cloud, cyber, technology, solution, success (alone)
❌ No merch/art queries: no "shirt", "poster", "art", "drawing", "wallpaper"
❌ No single-word or 2-word queries

API CHOICE RULES:
- SERPER  → Google Images. Use ONLY for named brands, specific people, specific city landmarks.
            Examples: "Ford F-150 2024 red truck exterior side view",
                      "Elon Musk speaking at product launch on stage",
                      "New York City Times Square night lights aerial"
- PEXELS  → Stock video 15-20 seconds. Use for generic scenes, actions, environments.
            Examples: "businessman walking through busy downtown street cinematic",
                      "aerial drone shot green mountain forest at sunrise",
                      "construction workers building steel frame on sunny day"
- MERGE   → Named subject image (Serper) + action/environment video (Pexels) spliced.
            serper_keyword = the specific named subject
            pexels_keyword = the action or environment around it
            Example: serper="Tesla Model 3 white exterior side view",
                     pexels="electric car driving on highway at sunset cinematic"

Return ONLY a JSON array — no markdown, no explanation, no code fences:
[
  {{
    "idx": 0,
    "visual_scene": "One sentence: exactly what the camera frame shows",
    "primary_keyword": "highly specific 5-8 word stock footage search query",
    "fallback_keyword": "slightly broader 5-7 word fallback stock footage query",
    "api_choice": "SERPER|PEXELS|MERGE",
    "serper_keyword": null,
    "pexels_keyword": null
  }}
]

MEDIA SEGMENTS (the avatar script text shown during each B-roll window):
{segments_json}

Return the JSON array only. One entry per segment, idx matching the order above."""


# ---------------------------------------------------------------------------
# Per-segment Gemini enrichment prompt (used for analyze() fallback)
# ---------------------------------------------------------------------------

_GEMINI_PROMPT_TEMPLATE = """\
You are a professional video editor deciding exactly what B-roll footage to show for a script segment.

THINKING PROCESS:
Step 1 — VISUALIZE: What would a camera show? Describe the exact visual frame in one sentence.
Step 2 — GENERATE: Convert that visual description into highly specific stock footage search queries.

QUERY RULES:
- Every query MUST be 5+ words minimum
- Format: [subject] + [action] + [setting] + [mood/style]
- Replace abstract/emotional with VISIBLE actions:
  "success" → "executive celebrating promotion shaking hands in office"
  "growth"  → "green plant growing time-lapse in sunlight"
  "future"  → "modern city skyline aerial drone shot blue hour"
- Use stock-site descriptors: cinematic, aerial, close-up, 4K, golden hour, slow motion
- NEVER use alone: innovation, future, AI, digital, concept, data, cloud, smart, cyber

Return ONLY valid JSON:
{{
  "visual_scene": "One sentence: exactly what the camera frame shows",
  "primary_subject": "The exact concrete thing shown on screen",
  "subject_type": "product | person | place | concept | action",
  "visual_action": "What is visually happening (e.g. 'driving on sunlit highway')",
  "environment": "Where it takes place (e.g. 'modern open-plan office')",
  "mood": "cinematic | bright | dramatic | professional | warm | cold",
  "must_show": ["concrete", "visual", "element", "required"],
  "must_avoid": ["cartoon", "illustration", "watermark", "anime", "low quality"],
  "search_queries": [
    "most specific 6-8 word query with subject action setting mood",
    "second specific 5-7 word query different angle or setting",
    "medium 5-6 word fallback query",
    "broader 5 word fallback",
    "generic 5 word fallback"
  ],
  "scene_type": "specific | general | mixed",
  "keywords": ["concrete", "visual", "keywords"],
  "named_entities": ["Named Entity If Present"]
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
        key_visuals = self.global_topic_info.get("key_visuals", [])
        context_phrases = self.global_topic_info.get("context_phrases", [])
        script_preview = self._full_script[:800].replace("\n", " ")

        # Build segments JSON — what the avatar says during each media window
        segments = [
            {"idx": i, "segment_text": block.script_text[:400]}
            for i, (_, block) in enumerate(media_blocks)
        ]
        segments_json = json.dumps(segments, indent=2)

        prompt = _BATCH_KEYWORDS_PROMPT.format(
            global_topic=global_topic or "general topic",
            key_visuals=", ".join(key_visuals) if key_visuals else "see script",
            context_phrases=", ".join(context_phrases) if context_phrases else "",
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

            primary_kw = str(entry.get("primary_keyword") or "").strip()
            fallback_kw = str(entry.get("fallback_keyword") or "").strip()

            # Enforce minimum 5-word queries — pad with topic context if too short
            primary_kw = self._ensure_rich_query(primary_kw, global_topic)
            fallback_kw = self._ensure_rich_query(fallback_kw, global_topic)

            plans[block_idx] = MediaPlan(
                primary_keyword=primary_kw,
                fallback_keyword=fallback_kw,
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
        key_visuals = self.global_topic_info.get("key_visuals", [])
        intent = extract_visual_intent(block.script_text, global_topic=global_topic)

        subject = intent.primary_subject or global_topic or "person"
        action = intent.action or "working"
        env = intent.environment or "outdoors"
        mood = intent.mood or "cinematic"

        # Build 5+ word queries
        primary = f"{subject} {action} {env} {mood}".strip()
        fallback = (
            f"{global_topic} {action} {env} cinematic".strip()
            if global_topic and global_topic.lower() not in subject.lower()
            else f"{subject} {env} professional shot"
        )

        # Enrich with key visuals if subject is generic
        if len(subject.split()) <= 1 and key_visuals:
            primary = f"{key_visuals[0]} {action} {env} {mood}".strip()

        from super_auto_editor_v2.analyze.scene_classifier import _has_known_brand
        use_serper = _has_known_brand(block.script_text.lower())

        return MediaPlan(
            primary_keyword=self._ensure_rich_query(primary, global_topic),
            fallback_keyword=self._ensure_rich_query(fallback, global_topic),
            api_choice="SERPER" if use_serper else "PEXELS",
        )

    def _ensure_rich_query(self, query: str, global_topic: str) -> str:
        """
        Guarantee the query has at least 5 words.
        If it's too short, pad it with global topic context and stock descriptors.
        """
        words = query.split()
        if len(words) >= 5:
            return query
        # Pad with global topic if it adds new info
        if global_topic and global_topic.lower() not in query.lower():
            query = f"{global_topic} {query}".strip()
        words = query.split()
        # Still short — add cinematic descriptor
        if len(words) < 5:
            padding = ["cinematic", "professional shot", "high quality footage"]
            for p in padding:
                query = f"{query} {p}"
                if len(query.split()) >= 5:
                    break
        return query.strip()

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

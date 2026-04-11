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

    def _analyze_with_gemini(self, text: str) -> dict[str, Any] | None:
        if not genai:
            return None
        prompt = (
            "Extract JSON with keys: keywords (array), named_entities (array). "
            "Return only JSON. Text:\n"
            f"{text}"
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

    def _heuristic_analyze(self, text: str) -> dict[str, Any]:
        tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", text)
        stop_words = {
            "the", "and", "for", "with", "this", "that", "from", "into", "then",
            "when", "where", "your", "their", "have", "will", "about", "video",
        }
        keywords = [t for t in tokens if t.lower() not in stop_words and len(t) > 2][:8]
        named_entities = []
        for i, token in enumerate(tokens):
            if token[:1].isupper() and token.lower() not in stop_words:
                if i + 1 < len(tokens) and tokens[i + 1][:1].isupper():
                    named_entities.append(f"{token} {tokens[i + 1]}")
                elif i > 0 and (any(ch.isdigit() for ch in token) or token.isupper()):
                    named_entities.append(token)
        dedup_entities = list(dict.fromkeys(named_entities))[:4]
        return {"keywords": keywords, "named_entities": dedup_entities}

    def _build_queries(
        self,
        text: str,
        scene_type: str,
        keywords: list[str],
        entities: list[str],
    ) -> list[str]:
        banned = {"it", "this", "that", "they", "we", "you", "he", "she"}
        if scene_type == "specific":
            # Keep exact phrase first for named/product scenes; avoids vague query drift.
            exact_phrase = " ".join(text.split()[:8]).strip()
            base = entities[0] if entities else (exact_phrase or " ".join(keywords[:3]))
            variants = [
                base,
                f"{base} front view",
                f"{base} side view",
                f"{base} driving road",
                f"{base} exterior",
                f"{base} close up",
                f"{base} high quality",
            ]
            # 7 targeted query variants for better Brave recall on specific scenes.
            return [q.strip() for q in variants if q.strip() and q.strip().lower() not in banned][:7]

        top = " ".join(keywords[:3]) if keywords else text[:50]
        return [
            top,
            f"{top} cinematic",
            f"{top} 4k landscape",
        ]

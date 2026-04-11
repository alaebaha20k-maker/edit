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
        self.main_subject = ""
        if gemini_api_key and genai:
            genai.configure(api_key=gemini_api_key)

    def set_context(self, full_script: str) -> None:
        tokens = re.findall(r"[A-Za-z0-9\\-]+", full_script)
        if not tokens:
            self.main_subject = ""
            return
        # simple, fast heuristic: earliest meaningful phrase anchors topic.
        self.main_subject = " ".join(tokens[:3]).strip()

    def analyze(self, block: TimelineBlock) -> SceneAnalysis:
        data = self._analyze_with_gemini(block.script_text) if self.gemini_api_key else None
        if not data:
            data = self._heuristic_analyze(block.script_text)

        scene_type = data.get("scene_type") or classify_scene_type(block.script_text, data.get("named_entities", []))
        source: MediaSource = "brave_images" if scene_type == "specific" else "pexels_video"
        queries = self._build_queries(
            text=block.script_text,
            scene_type=scene_type,
            keywords=data.get("keywords", []),
            entities=data.get("named_entities", []),
            subject=str(data.get("subject") or "").strip(),
        )
        gemini_queries = data.get("search_queries")
        if isinstance(gemini_queries, list) and gemini_queries:
            queries = [str(q).strip() for q in gemini_queries if str(q).strip()][:7] or queries
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
            "Extract visual-beat JSON with keys: keywords (array), named_entities (array), "
            "scene_type ('specific' or 'general'), subject, action, environment, mood, style, "
            "search_queries (array of 5-8 queries, each 4-10 words, each must include subject+action+environment), "
            "negative_keywords (array). "
            "Focus on physically filmable visuals only; avoid abstract-only wording. "
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
            parsed = json.loads(raw[start : end + 1])
            if parsed.get("scene_type") not in ("specific", "general"):
                parsed["scene_type"] = None
            return parsed
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
        scene_type = classify_scene_type(text, dedup_entities)
        subject, action, environment = self._heuristic_visual_parts(text, keywords, dedup_entities)
        search_queries = self._build_visual_queries(subject, action, environment, scene_type)
        return {
            "keywords": keywords,
            "named_entities": dedup_entities,
            "scene_type": scene_type,
            "subject": subject,
            "action": action,
            "environment": environment,
            "search_queries": search_queries,
            "negative_keywords": ["cartoon", "illustration", "animation"],
        }

    def _heuristic_visual_parts(self, text: str, keywords: list[str], entities: list[str]) -> tuple[str, str, str]:
        words = [w.lower() for w in re.findall(r"[A-Za-z0-9\\-]+", text)]
        subject = entities[0] if entities else (keywords[0] if keywords else "person")
        action_verbs = ["walking", "working", "talking", "driving", "typing", "looking", "sitting", "running"]
        env_terms = ["office", "street", "city", "room", "forest", "studio", "meeting", "home", "night"]
        action = next((w for w in words if w in action_verbs), "working")
        environment = next((w for w in words if w in env_terms), "office")
        return subject, action, environment

    def _build_visual_queries(self, subject: str, action: str, environment: str, scene_type: str) -> list[str]:
        base = f"{subject} {action} {environment}".strip()
        variants = [
            base,
            f"{subject} {action} in {environment}",
            f"{subject} {action} {environment} wide shot",
            f"{subject} {action} {environment} close up",
            f"{subject} {action} {environment} cinematic",
        ]
        if scene_type == "general":
            variants.append(f"{subject} {action} {environment} b-roll")
        return [q for q in variants if len(q.split()) <= 10][:8]

    def _build_queries(
        self,
        text: str,
        scene_type: str,
        keywords: list[str],
        entities: list[str],
        subject: str = "",
    ) -> list[str]:
        banned = {"it", "this", "that", "they", "we", "you", "he", "she"}
        primary_subject = subject or (entities[0] if entities else " ".join(keywords[:2]))
        if scene_type == "specific":
            # Subject-first query strategy: keep query simple and object-focused.
            base = primary_subject.strip() or "subject"
            if self.main_subject and self.main_subject.lower() not in base.lower():
                base = f"{self.main_subject} {base}".strip()
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

        top = primary_subject.strip() or (" ".join(keywords[:3]) if keywords else text[:50])
        if self.main_subject and self.main_subject.lower() not in top.lower():
            top = f"{self.main_subject} {top}".strip()
        return [
            top,
            f"{top} cinematic b-roll",
            f"{top} moody lighting 4k",
        ]

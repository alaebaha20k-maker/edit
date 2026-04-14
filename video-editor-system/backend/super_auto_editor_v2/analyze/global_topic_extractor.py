from __future__ import annotations

"""
global_topic_extractor.py
------------------------
Extract the main topic of the ENTIRE script to use as fallback context
when scene-level subject extraction fails.

SOLVES CRITICAL BUG: Without this, scenes extract stop words (The, That, They)
as subjects, resulting in queries like "The showing" instead of "barndominium wraparound porch".

Strategy:
1. Count noun frequency in full script (exclude stop words)
2. Extract first mentioned topic from script opening
3. (Optional) Use Gemini for semantic understanding

Result: When a scene says "That modern farmhouse...", we know the global
topic is "barndominium", so we use that as fallback.
"""

import re
from typing import Any

try:
    import google.generativeai as genai
except Exception:
    genai = None


# Expanded stop words — includes ALL pronouns, articles, common verbs
STOP_WORDS_GLOBAL: frozenset[str] = frozenset({
    # Articles
    "the", "a", "an",
    # Pronouns (CRITICAL - these were the root cause of the bug)
    "this", "that", "these", "those", "it", "its", "itself",
    "you", "your", "yours", "yourself", "yourselves",
    "we", "our", "ours", "us", "ourselves",
    "they", "their", "theirs", "them", "themselves",
    "he", "his", "him", "himself",
    "she", "her", "hers", "herself",
    "i", "me", "my", "mine", "myself",
    "who", "whom", "whose",
    # Common verbs
    "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "having",
    "do", "does", "did", "doing",
    "will", "would", "could", "should", "may", "might", "must",
    "can", "shall",
    # Prepositions
    "in", "on", "at", "to", "for", "of", "with", "by",
    "from", "into", "onto", "upon", "about", "above", "below",
    "between", "under", "over", "through", "during", "before", "after",
    # Conjunctions
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
    # Adverbs
    "not", "no", "never", "always", "often", "sometimes", "usually",
    "very", "really", "just", "only", "also", "too", "even",
    # Other common words
    "when", "where", "why", "how", "what", "which",
    "there", "here", "then", "now", "today", "tomorrow", "yesterday",
    "if", "because", "although", "unless", "while", "until", "since",
    # Video/content meta-words (not visual)
    "video", "watch", "see", "look", "show", "shows", "showing",
    "let", "lets", "going", "want", "needs", "need", "think", "know",
    "make", "makes", "come", "comes", "take", "takes", "get", "gets",
    "like", "likes", "find", "finds", "use", "uses", "give", "gives",
    "say", "says", "tell", "tells", "call", "calls", "mean", "means",
})


class GlobalTopicExtractor:
    """Extract the main topic of the entire script for context."""

    def __init__(self, gemini_api_key: str = ""):
        self.gemini_api_key = gemini_api_key
        if gemini_api_key and genai:
            genai.configure(api_key=gemini_api_key)

    def extract(self, full_script: str) -> dict[str, Any]:
        """
        Extract global topic info from the full script.

        Returns:
        {
            "main_topic": "barndominium",
            "topic_type": "product|service|concept|place|tutorial",
            "key_visuals": ["visual1", "visual2", ...],
            "context_phrases": ["phrase1", "phrase2", ...],
        }
        """
        # Try Gemini first (if available)
        if self.gemini_api_key:
            result = self._extract_with_gemini(full_script)
            if result:
                return result

        # Fallback to heuristic
        return self._extract_heuristic(full_script)

    # ------------------------------------------------------------------
    # Gemini path
    # ------------------------------------------------------------------

    def _extract_with_gemini(self, full_script: str) -> dict[str, Any] | None:
        if not genai:
            return None

        prompt = f"""Analyze this video script and extract:

1. MAIN_TOPIC: The primary subject in 1-3 words (e.g., "barndominium designs")
2. TOPIC_TYPE: One of [product, service, concept, place, tutorial]
3. KEY_VISUALS: 5 things that MUST appear in every scene's visuals
4. CONTEXT_PHRASES: 3-5 phrases to enrich every search query

Script (first 2000 chars):
{full_script[:2000]}

Return JSON only with keys: main_topic, topic_type, key_visuals (array), context_phrases (array)."""

        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            resp = model.generate_content(prompt)
            raw = (resp.text or "").strip()
            start = raw.find("{")
            end = raw.rfind("}")
            if start == -1 or end == -1:
                return None
            import json
            parsed = json.loads(raw[start : end + 1])
            return {
                "main_topic": str(parsed.get("main_topic") or "").strip(),
                "topic_type": str(parsed.get("topic_type") or "concept").strip(),
                "key_visuals": [str(v) for v in (parsed.get("key_visuals") or [])],
                "context_phrases": [str(p) for p in (parsed.get("context_phrases") or [])],
            }
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Heuristic fallback
    # ------------------------------------------------------------------

    def _extract_heuristic(self, full_script: str) -> dict[str, Any]:
        """Fast word-frequency analysis without API calls."""
        text_lower = full_script.lower()

        # Step 1: Count noun frequencies
        words = re.findall(r"\b[a-z]{4,}\b", text_lower)
        word_freq: dict[str, int] = {}
        for w in words:
            if w not in STOP_WORDS_GLOBAL:
                word_freq[w] = word_freq.get(w, 0) + 1

        # Top words = likely topics
        top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:10]
        main_topic = top_words[0][0] if top_words else "subject"

        # Step 2: Find topic type hints in script
        topic_type = self._detect_topic_type(text_lower, main_topic)

        # Step 3: Extract key visuals from first paragraph
        key_visuals = self._extract_key_visuals(full_script[:1000], main_topic)

        # Step 4: Build context phrases
        context_phrases = [main_topic]
        if len(top_words) > 1:
            context_phrases.append(top_words[1][0])
        if len(top_words) > 2:
            context_phrases.append(top_words[2][0])

        return {
            "main_topic": main_topic,
            "topic_type": topic_type,
            "key_visuals": key_visuals,
            "context_phrases": list(dict.fromkeys(context_phrases)),
        }

    def _detect_topic_type(self, text: str, main_topic: str) -> str:
        """Detect if main topic is product/service/concept/place/tutorial."""
        type_hints = {
            "product": [
                "model", "design", "feature", "new", "release", "launch",
                "price", "cost", "buy", "purchase", "available",
                main_topic,
            ],
            "service": [
                "service", "offer", "provide", "help", "support",
                "subscription", "plan", "package",
            ],
            "tutorial": [
                "how to", "build", "make", "create", "install",
                "setup", "configure", "step", "guide", "learn",
                "teach", "show", "demonstrate",
            ],
            "place": [
                "location", "building", "home", "house", "city",
                "state", "country", "area", "region", "tour",
            ],
        }

        scores: dict[str, int] = {t: 0 for t in type_hints}
        for ttype, hints in type_hints.items():
            for hint in hints:
                if hint in text:
                    scores[ttype] += text.count(hint)

        best_type = max(scores, key=lambda k: scores[k])
        return best_type if scores[best_type] > 0 else "concept"

    def _extract_key_visuals(self, excerpt: str, main_topic: str) -> list[str]:
        """Extract 5 key visual elements from script opening."""
        visuals = [main_topic]

        # Look for descriptive phrases with common visual adjectives
        visual_adjectives = [
            "modern", "beautiful", "large", "open", "custom", "unique",
            "stunning", "elegant", "spacious", "bright", "glass",
            "steel", "exterior", "interior", "view", "style",
        ]

        # Extract title-case compounds (e.g., "Floor-to-Ceiling Windows")
        title_compounds = re.findall(
            r"\b([A-Z][a-z]+(?:[-\s]+[A-Z][a-z]+)*)\b", excerpt
        )
        visuals.extend([c for c in title_compounds if len(c) > 3])

        # Extract quoted descriptive phrases
        quoted = re.findall(r'"([^"]{10,100})"', excerpt)
        visuals.extend(quoted)

        # Dedupe and return top 5
        seen: set[str] = set()
        result = []
        for v in visuals:
            v_lower = v.lower()
            if v_lower not in seen:
                seen.add(v_lower)
                result.append(v)
        return result[:5]

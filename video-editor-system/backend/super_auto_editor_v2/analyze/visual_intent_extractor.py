from __future__ import annotations

"""
visual_intent_extractor.py
--------------------------
Extracts structured visual intent from script text:
  - WHAT to show (primary subject)
  - HOW (action / visual style)
  - WHERE (environment)
  - MUST_SHOW / MUST_AVOID lists for relevance filtering

Used by ScriptAnalyzer before scene classification so that every
downstream component gets rich, precise signal instead of bare keywords.
"""

import re

from super_auto_editor_v2.analyze.global_topic_extractor import STOP_WORDS_GLOBAL
from super_auto_editor_v2.models import VisualIntent


# ---------------------------------------------------------------------------
# Static vocabulary tables
# ---------------------------------------------------------------------------

ACTION_VERBS: list[str] = [
    # Only VISUAL actions — abstract/meta verbs excluded intentionally
    # ("showing", "displaying", "presenting" produce nonsense queries like "truck showing")
    "driving", "walking", "running", "sitting", "standing",
    "using", "holding", "working", "typing", "talking", "looking",
    "riding", "flying", "swimming", "cooking", "eating", "drinking",
    "launching", "demonstrating", "exploring",
    "building", "creating", "streaming", "playing",
]

ENVIRONMENT_WORDS: list[str] = [
    "road", "highway", "city", "office", "home", "studio",
    "showroom", "street", "park", "building", "interior", "exterior",
    "mountain", "beach", "forest", "desert", "urban", "rural",
    "stage", "arena", "lab", "factory", "restaurant", "hotel",
    "stadium", "airport", "store", "mall", "gym", "school",
]

MOOD_WORDS: list[str] = [
    "cinematic", "dramatic", "bright", "dark", "vibrant", "moody",
    "energetic", "peaceful", "emotional", "inspiring", "powerful",
    "sleek", "elegant", "futuristic", "vintage", "modern", "luxury",
]

AVOID_DEFAULTS: list[str] = [
    "cartoon", "illustration", "anime", "drawing", "clipart",
    "low quality", "watermark", "blurry", "stock photo watermark",
]

# Patterns for product/brand names (multi-word, optionally with year / suffix)
# IMPORTANT: Only match REAL products, not arbitrary capitalized words
PRODUCT_PATTERNS: list[str] = [
    # Apple products
    r"\b(iPhone|iPad|MacBook|iMac|AirPods|Apple Watch|iWatch)\s*(?:Pro|Max|Ultra|Plus|Mini|Air)?\s*(?:\d{1,4})?\b",
    # Android/Samsung devices
    r"\b(Galaxy|Pixel|Surface|Xperia|OnePlus)\s*(?:Pro|Max|Ultra|Plus|Fold|Note|S|Z)?\s*(?:\d{1,4})?\b",
    # Car brands + model (MUST have brand name)
    r"\b(Ford|Toyota|Honda|BMW|Mercedes|Audi|Tesla|Chevrolet|Volkswagen|Nissan|Hyundai|Kia|Mazda|Subaru|Lexus)\s+([A-Z][a-z0-9\s]+?)(?:\s*\d{4})?\b",
    # Specific car models (Focus, Mustang, etc.)
    r"\b(Model\s+[SXYZ3Y]|Mustang|Camaro|Civic|Accord|Corolla|Focus|Fusion|Ranger|F-150|Silverado|Ram)\b",
    # Brand + Year (must be a KNOWN brand)
    r"\b(Ford|Toyota|Honda|BMW|Mercedes|Tesla|Apple|Samsung|Google)\s+\d{4}\b",
    # Year + Brand
    r"\b\d{4}\s+(Ford|Toyota|Honda|BMW|Mercedes|Tesla|Apple|Samsung)\b",
    # Model numbers (RTX-4090, RTX 4090)
    r"\b[A-Z]{2,5}[-\s]?\d{3,4}\b",
]

SUBJECT_TYPE_HINTS: dict[str, list[str]] = {
    "product": [
        "phone", "car", "truck", "suv", "laptop", "tablet", "watch", "camera",
        "headphones", "tv", "monitor", "console", "speaker", "drone", "robot",
        "model", "version", "edition", "series", "pro", "max", "ultra",
    ],
    "person": [
        "ceo", "founder", "president", "director", "actor", "singer", "athlete",
        "scientist", "engineer", "doctor", "expert", "analyst",
        "announced", "said", "stated", "revealed", "declared",
    ],
    "place": [
        "city", "country", "state", "island", "mountain", "river", "lake",
        "ocean", "park", "street", "avenue", "building", "tower", "bridge",
        "museum", "stadium", "airport", "port",
    ],
    "concept": [
        "success", "failure", "growth", "decline", "future", "past",
        "technology", "innovation", "creativity", "strategy", "vision",
        "freedom", "peace", "war", "love", "happiness", "fear",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_visual_intent(text: str, global_topic: str = "") -> VisualIntent:
    """
    Fast heuristic extraction of visual intent from a script segment.
    No external API calls.  Returns a VisualIntent with as much detail
    as possible; callers can always refine with Gemini results.
    """
    words_raw = re.findall(r"[A-Za-z0-9']+", text)
    words_lower = [w.lower() for w in words_raw]

    primary_subject = _extract_primary_subject(text, words_lower, global_topic)
    subject_type = _detect_subject_type(primary_subject, words_lower)
    action = _find_first(words_lower, ACTION_VERBS) or ""
    environment = _find_first(words_lower, ENVIRONMENT_WORDS) or ""
    mood = _find_first(words_lower, MOOD_WORDS) or "cinematic"

    must_show = _build_must_show(primary_subject, subject_type)
    must_avoid = list(AVOID_DEFAULTS)

    search_queries = _build_initial_queries(
        primary_subject, subject_type, action, environment, global_topic
    )

    return VisualIntent(
        primary_subject=primary_subject,
        subject_type=subject_type,
        action=action,
        environment=environment,
        mood=mood,
        must_show=must_show,
        must_avoid=must_avoid,
        search_queries=search_queries,
    )


def merge_gemini_intent(base: VisualIntent, gemini_data: dict) -> VisualIntent:
    """
    Overlay Gemini-parsed fields on top of the heuristic VisualIntent.
    Gemini wins on subject / type / queries; heuristics fill gaps.
    """
    subject = str(gemini_data.get("primary_subject") or gemini_data.get("subject") or "").strip()
    if subject:
        base.primary_subject = subject

    stype = str(gemini_data.get("subject_type") or "").strip().lower()
    if stype in SUBJECT_TYPE_HINTS:
        base.subject_type = stype

    action = str(gemini_data.get("visual_action") or gemini_data.get("action") or "").strip()
    if action:
        base.action = action

    env = str(gemini_data.get("environment") or "").strip()
    if env:
        base.environment = env

    mood = str(gemini_data.get("mood") or "").strip()
    if mood:
        base.mood = mood

    must_show_raw = gemini_data.get("must_show") or []
    if isinstance(must_show_raw, list):
        base.must_show = [str(x) for x in must_show_raw if x]

    must_avoid_raw = gemini_data.get("must_avoid") or []
    if isinstance(must_avoid_raw, list):
        extra_avoid = [str(x) for x in must_avoid_raw if x]
        base.must_avoid = list(dict.fromkeys(base.must_avoid + extra_avoid))

    queries_raw = gemini_data.get("search_queries") or []
    if isinstance(queries_raw, list) and queries_raw:
        base.search_queries = [str(q).strip() for q in queries_raw if str(q).strip()][:10]

    return base


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _extract_primary_subject(text: str, words_lower: list[str], global_topic: str = "") -> str:
    """
    Extract the actual primary subject, NEVER returning stop words.
    CRITICAL BUG FIX: Previous code returned "The", "That", "They" as subjects!

    Strategy:
    1. Product patterns (brand+model)
    2. Title-case multi-word phrases (proper nouns)
    3. Quoted phrases
    4. Hyphenated compounds (wraparound porch, floor-to-ceiling, u-shaped)
    5. Adjective + noun compounds
    6. Capitalised words (not sentence starts)
    7. Global topic fallback
    8. Generic "subject"
    """
    # 1. Product / brand patterns (most specific)
    for pattern in PRODUCT_PATTERNS:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(0).strip()
            if len(candidate) > 2 and candidate.lower() not in STOP_WORDS_GLOBAL:
                return candidate

    # 2. Multi-word title-case phrase (e.g. "Ford Focus", "U-shaped barndominium")
    # MUST have at least 2 words (the + ensures 1 or more additional words)
    title_phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z0-9]+)+)\b", text)
    if title_phrases:
        for phrase in title_phrases:
            phrase_lower = phrase.lower()
            # Skip sentence starters and stop words
            if phrase_lower not in STOP_WORDS_GLOBAL and len(phrase) > 3:
                return phrase

    # 3. Quoted phrases (highest semantic value)
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    if quoted:
        for q1, q2 in quoted:
            candidate = (q1 or q2).strip()
            if len(candidate) > 3:
                return candidate

    # 4. Hyphenated compounds first (floor-to-ceiling, U-shaped, etc.)
    hyphen_compounds = re.findall(r"\b([A-Za-z]+-[A-Za-z]+(?:-[A-Za-z]+)*)\b", text)
    if hyphen_compounds:
        for compound in hyphen_compounds:
            if compound.lower() not in STOP_WORDS_GLOBAL:
                return compound

    # 5. Adjective + noun compounds (look for adjective + noun with 5+ char noun)
    # Common adjectives that precede nouns in visual contexts
    common_adjectives = {
        "modern", "beautiful", "large", "open", "custom", "unique", "stunning",
        "elegant", "spacious", "bright", "glass", "steel", "wooden", "new",
        "old", "small", "big", "outdoor", "indoor", "exterior", "interior",
        "wraparound", "covered", "raised", "dramatic", "grand", "minimalist",
    }
    # Common verbs to EXCLUDE (don't confuse verbs with nouns).
    # Includes 3rd-person singular forms (-s/-es) that look like nouns.
    common_verbs = {
        "provides", "creates", "features", "offers", "becomes", "seems",
        "appears", "stands", "shows", "includes", "contains", "requires",
        # Motion / action verbs (present tense 3rd-person)
        "drives", "rides", "runs", "walks", "flies", "swims", "talks",
        "moves", "works", "plays", "builds", "makes", "takes", "gives",
        "lives", "comes", "goes", "starts", "stops", "turns", "looks",
        "brings", "keeps", "leads", "means", "needs", "puts", "sets",
    }

    # Convert to lowercase for pattern matching but preserve original case
    text_lower = text.lower()
    adj_noun_pattern = r"\b([a-z]{4,})\s+([a-z]{5,})\b"
    matches = re.findall(adj_noun_pattern, text_lower)
    if matches:
        # Find the BEST match (adjective in our list)
        for adj, noun in matches:
            if (adj in common_adjectives and
                noun not in STOP_WORDS_GLOBAL and
                noun not in common_verbs):
                # Return with proper capitalization
                return f"{adj} {noun}"
        # Fallback: if no "common adjective" match, still accept good adj+noun pairs
        for adj, noun in matches:
            if (adj not in STOP_WORDS_GLOBAL and
                noun not in STOP_WORDS_GLOBAL and
                noun not in common_verbs and
                len(f"{adj} {noun}") > 8):
                return f"{adj} {noun}"

    # 6. Single capitalised word (not a sentence start, and NOT a stop word)
    cap_words = [w for w in re.findall(r"\b([A-Z][a-z]{3,})\b", text)]
    sentence_starts = {s.split()[0] for s in re.split(r"[.!?]", text) if s.strip()}
    non_start_caps = [w for w in cap_words if w not in sentence_starts and w.lower() not in STOP_WORDS_GLOBAL]
    if non_start_caps:
        return non_start_caps[0]

    # 7. Fallback to first meaningful noun token (length > 4, not a stop word)
    meaningful = [w for w in words_lower if w not in STOP_WORDS_GLOBAL and len(w) > 4]
    if meaningful:
        return meaningful[0]

    # 8. Last resort: use global topic if available, otherwise generic
    if global_topic and global_topic.lower() not in STOP_WORDS_GLOBAL:
        return global_topic

    return "subject"


def _detect_subject_type(subject: str, words_lower: list[str]) -> str:
    subject_lower = subject.lower()
    scores: dict[str, int] = {t: 0 for t in SUBJECT_TYPE_HINTS}
    for stype, hints in SUBJECT_TYPE_HINTS.items():
        for h in hints:
            if h in subject_lower or h in words_lower:
                scores[stype] += 1
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "concept"


def _build_must_show(subject: str, subject_type: str) -> list[str]:
    must: list[str] = []
    if subject and subject != "subject":
        must.append(subject)
    if subject_type == "product":
        must.extend(["real photo", "high resolution"])
    elif subject_type == "person":
        must.extend(["person", "face"])
    elif subject_type == "place":
        must.extend(["outdoor", "real photo"])
    return must


def _build_initial_queries(
    subject: str,
    subject_type: str,
    action: str,
    environment: str,
    global_topic: str = "",
) -> list[str]:
    # Enrich queries with global topic when subject is missing that context.
    # e.g. subject="truck", global_topic="Ford F-150" → first query "Ford F-150 truck"
    topic_adds_context = (
        global_topic
        and global_topic.lower() not in subject.lower()
        and subject.lower() not in global_topic.lower()
    )

    queries: list[str] = []
    if subject_type in ("product", "person", "place"):
        queries = [
            # Global topic + subject as the most specific first query
            f"{global_topic} {subject}".strip() if topic_adds_context else subject,
            f"{subject} official photo",
            f"{subject} {action}".strip() if action else f"{subject} high resolution",
            f"{subject} {environment}".strip() if environment else f"{subject} exterior",
            f"{subject} press photo",
            f"{subject}",
        ]
    else:
        mood = "cinematic"
        queries = [
            f"{global_topic} {subject} {action} {environment}".strip() if topic_adds_context
            else f"{subject} {action} {environment}".strip(),
            f"{subject} {action} {environment}".strip(),
            f"{subject} {mood}",
            f"{action} {environment} {mood} b-roll".strip(),
            subject,
        ]
    return [q.strip() for q in queries if q.strip() and len(q.strip()) > 3][:8]


def _find_first(words: list[str], vocab: list[str]) -> str:
    for w in words:
        if w in vocab:
            return w
    return ""

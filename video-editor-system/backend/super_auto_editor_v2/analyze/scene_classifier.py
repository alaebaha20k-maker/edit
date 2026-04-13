from __future__ import annotations

"""
scene_classifier.py
-------------------
Classify a script segment as:
  "specific"  - shows a named product / person / place  → Brave images primary
  "general"   - generic concept / mood / B-roll         → Pexels video primary
  "mixed"     - has a specific subject AND an action    → both sources combined

Priority chain:
  1. Known brand / product name detected
  2. VisualIntent says subject_type is product/person/place
  3. Product pattern regex match
  4. Named entity (title-case multi-word)
  5. Only mark general when text is truly abstract

The "mixed" type is NEW: allows the pipeline to fetch a subject image
(Brave) and a supporting environment video (Pexels) and splice them.
"""

import re

from super_auto_editor_v2.models import SceneType

# ---------------------------------------------------------------------------
# Brand / product knowledge base
# ---------------------------------------------------------------------------

KNOWN_BRANDS: frozenset[str] = frozenset({
    # Cars
    "ford", "toyota", "honda", "bmw", "mercedes", "audi", "tesla",
    "chevrolet", "volkswagen", "nissan", "hyundai", "kia", "mazda",
    "subaru", "lexus", "volvo", "dodge", "jeep", "ram", "chrysler",
    "cadillac", "lincoln", "buick", "gmc", "acura", "infiniti",
    "porsche", "ferrari", "lamborghini", "maserati", "jaguar", "landrover",
    "bentley", "rolls-royce", "bugatti", "pagani", "rivian", "lucid",
    "polestar", "genesis", "fiat", "alfa romeo", "seat",
    # Tech - devices
    "apple", "samsung", "google", "microsoft", "sony", "lg", "dell",
    "hp", "lenovo", "asus", "acer", "razer", "alienware", "huawei",
    "oneplus", "xiaomi", "oppo", "vivo", "realme", "motorola", "nokia",
    # Tech - products (by name, not brand)
    "iphone", "ipad", "macbook", "imac", "airpods", "apple watch",
    "galaxy", "pixel", "surface", "xperia", "zenfone",
    "playstation", "xbox", "nintendo", "switch", "ps5", "ps4",
    # Tech - companies / platforms
    "nvidia", "amd", "intel", "qualcomm", "arm", "tsmc",
    "meta", "instagram", "facebook", "twitter", "x", "tiktok",
    "youtube", "spotify", "netflix", "amazon", "uber", "airbnb",
    "openai", "anthropic", "gemini", "chatgpt", "midjourney",
    # Consumer brands
    "nike", "adidas", "puma", "under armour", "new balance",
    "coca-cola", "pepsi", "redbull", "monster", "starbucks",
    "mcdonalds", "kfc", "burger king", "subway",
    "louis vuitton", "gucci", "prada", "chanel", "rolex",
    "dyson", "bosch", "siemens", "philips", "panasonic",
})

# Model / product regex patterns
PRODUCT_PATTERNS: list[str] = [
    r"\b(iPhone|iPad|MacBook|iMac|AirPods|Apple Watch)\s*(?:Pro|Max|Ultra|Plus|Mini|Air)?\s*(?:\d{1,4})?\b",
    r"\b(Galaxy|Pixel|Surface|Xperia)\s*(?:\w+)?\b",
    r"\b(Model\s+[SX3Y]|Mustang|Camaro|Civic|Accord|Corolla|Camry|F-150|Silverado|RAM\s+\d{3,4})\b",
    r"\b([A-Z][a-z]+)\s+(Focus|Fusion|Explorer|Ranger|Bronco|Prius|RAV4|CR-V|HR-V|Tucson|Seltos)\b",
    r"\b\w+\s+\d{4}\b",            # "Focus 2024", "iPhone 2023"
    r"\b\d{4}\s+[A-Z][a-z]+\b",    # "2024 Ford"
    r"\b[A-Z]{2,5}-?\d{3,4}\b",    # "RTX-4090", "GTX1080"
    r"\bRTX\s*\d{4}\b",
    r"\bGeForce\s+\w+\b",
    r"\bCore\s+i[3579]\b",
    r"\bRyzen\s+\d\b",
]

STOP_WORDS: frozenset[str] = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "into", "then",
    "when", "where", "your", "their", "have", "will", "about", "video",
    "scene", "show", "shows", "a", "an", "in", "on", "at", "to", "of",
    "is", "are", "was", "were", "be", "been", "has", "had", "do", "does",
    "did", "it", "its", "they", "we", "you", "he", "she", "i", "me", "my",
})

# Words that by themselves are truly generic (only trigger "general" when
# no brand / entity is present)
TRULY_GENERIC: frozenset[str] = frozenset({
    "success", "motivation", "happiness", "peace", "fear", "love",
    "journey", "growth", "nature", "freedom", "inspiration", "life",
    "future", "past", "history", "economy", "society", "culture",
    "beauty", "strength", "courage", "hope", "faith", "trust",
})


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------

def classify_scene_type(
    text: str,
    entities: list[str],
    subject_type: str = "",
) -> SceneType:
    """
    Classify a script segment into 'specific', 'general', or 'mixed'.

    Parameters
    ----------
    text : str
        The raw script segment.
    entities : list[str]
        Named entities extracted by the script analyser.
    subject_type : str
        Optional subject type from VisualIntent ('product', 'person', etc.).
    """
    lower = text.lower()
    words = re.findall(r"[A-Za-z0-9]+", text)
    content_words = [w for w in words if w.lower() not in STOP_WORDS]

    # ------------------------------------------------------------------
    # Priority 1: VisualIntent already determined subject type
    # ------------------------------------------------------------------
    if subject_type in ("product", "person", "place"):
        # If there is also an action/environment word → mixed
        has_env = any(env in lower for env in _ENVIRONMENT_WORDS)
        if has_env:
            return "mixed"
        return "specific"

    # ------------------------------------------------------------------
    # Priority 2: Known brand appears in text
    # ------------------------------------------------------------------
    if _has_known_brand(lower):
        has_env = any(env in lower for env in _ENVIRONMENT_WORDS)
        return "mixed" if has_env else "specific"

    # ------------------------------------------------------------------
    # Priority 3: Product pattern regex
    # ------------------------------------------------------------------
    for pattern in PRODUCT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            has_env = any(env in lower for env in _ENVIRONMENT_WORDS)
            return "mixed" if has_env else "specific"

    # ------------------------------------------------------------------
    # Priority 4: Named entity present
    # ------------------------------------------------------------------
    if entities:
        return "specific"

    # ------------------------------------------------------------------
    # Priority 5: Quoted phrase (multi-word) → specific
    # ------------------------------------------------------------------
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
    flat_quoted = [q1 or q2 for q1, q2 in quoted]
    if any(len(q.split()) >= 2 for q in flat_quoted):
        return "specific"

    # ------------------------------------------------------------------
    # Priority 6: Title-case multi-word phrase (potential named entity)
    # ------------------------------------------------------------------
    title_phrases = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    if title_phrases:
        return "specific"

    # ------------------------------------------------------------------
    # Priority 7: Truly generic / abstract → general
    # ------------------------------------------------------------------
    word_set = {w.lower() for w in words}
    if word_set & TRULY_GENERIC and not _has_known_brand(lower):
        return "general"

    # ------------------------------------------------------------------
    # Priority 8: Very short, non-abstract segment → specific (safer)
    # ------------------------------------------------------------------
    if 1 <= len(content_words) <= 4:
        return "specific"

    # ------------------------------------------------------------------
    # Default: lean general for long abstract sentences
    # ------------------------------------------------------------------
    return "general"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_known_brand(text_lower: str) -> bool:
    return any(brand in text_lower for brand in KNOWN_BRANDS)


_ENVIRONMENT_WORDS: frozenset[str] = frozenset({
    "road", "highway", "street", "city", "urban", "rural",
    "office", "home", "studio", "showroom", "indoor", "outdoor",
    "mountain", "beach", "forest", "desert", "park", "building",
    "stage", "arena", "lab", "factory", "track", "circuit",
})

"""
SEO Formula Manager - CRUD for named SEO formula presets
Each preset has a name and a formula text used to generate YouTube descriptions + tags.
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional


DEFAULT_FORMULA = """INSTRUCTIONS:
Write a high-quality YouTube description and tags for a video in the detected language.

DESCRIPTION STRUCTURE:
1. OPENING (2-3 sentences): Hook directly connected to the video title. Identify the viewer's problem.
2. BODY (3-5 bullet points with •): Key things the viewer will learn or discover from the video.
3. CTA SECTION: Natural mention of the product/link with a short compelling sentence about what's behind it.
   Format: 👉 {link}
4. CHAPTERS SECTION (⏱ CHAPITRES / ⏱ CHAPTERS):
   Format each chapter as: 00:00 — Chapter title
   Create 5-10 logical chapters from the script content.
5. CLOSING LINE: One line inviting to subscribe / follow.

TAGS RULES:
- Comma-separated, total MUST be under 400 characters
- Start with the most specific tags (exact title keywords), then broader related terms
- Mix short tags (2-3 words) and long-tail tags (4-5 words)
- All tags in the same language as the video

LANGUAGE: Auto-detect from title and script. Write EVERYTHING in that language."""


class SeoFormulaManager:
    """Manage named SEO formula presets."""

    FORMULAS_FILE = Path.home() / '.video-editor-data' / 'seo_formulas.json'

    @classmethod
    def _ensure_file(cls):
        cls.FORMULAS_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not cls.FORMULAS_FILE.exists():
            with open(cls.FORMULAS_FILE, 'w') as f:
                json.dump({"formulas": []}, f, indent=2)

    @classmethod
    def _load(cls) -> List[Dict]:
        cls._ensure_file()
        try:
            with open(cls.FORMULAS_FILE) as f:
                return json.load(f).get("formulas", [])
        except Exception:
            return []

    @classmethod
    def _save(cls, formulas: List[Dict]):
        with open(cls.FORMULAS_FILE, 'w') as f:
            json.dump({"formulas": formulas}, f, indent=2)

    @classmethod
    def get_all(cls) -> List[Dict]:
        return cls._load()

    @classmethod
    def get(cls, formula_id: str) -> Optional[Dict]:
        return next((f for f in cls._load() if f['id'] == formula_id), None)

    @classmethod
    def create(cls, name: str, formula: str) -> Dict:
        if not name or len(name.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        if not formula or len(formula.strip()) < 10:
            raise ValueError("Formula must be at least 10 characters")

        new = {
            "id": f"seo_{uuid.uuid4().hex[:8]}",
            "name": name.strip(),
            "formula": formula.strip(),
        }
        formulas = cls._load()
        formulas.append(new)
        cls._save(formulas)
        return new

    @classmethod
    def update(cls, formula_id: str, name: str = None, formula: str = None) -> Optional[Dict]:
        formulas = cls._load()
        idx = next((i for i, f in enumerate(formulas) if f['id'] == formula_id), None)
        if idx is None:
            return None
        if name is not None:
            formulas[idx]['name'] = name.strip()
        if formula is not None:
            formulas[idx]['formula'] = formula.strip()
        cls._save(formulas)
        return formulas[idx]

    @classmethod
    def delete(cls, formula_id: str) -> bool:
        formulas = cls._load()
        new_list = [f for f in formulas if f['id'] != formula_id]
        if len(new_list) == len(formulas):
            return False
        cls._save(new_list)
        return True

    @classmethod
    def get_default_formula_text(cls) -> str:
        return DEFAULT_FORMULA

"""
Video Style Manager - CRUD for video prompt styles
Each style has a name and a formula that guides the AI when writing
video prompts for generators like Sora, Runway, Kling, Pika.
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional


class VideoStyleManager:
    STYLES_FILE = Path.home() / '.video-editor-data' / 'video_styles.json'

    # Built-in read-only styles
    BUILTIN_STYLES = [
        {
            "id": "cinematic_video",
            "name": "Cinematic",
            "description": "Film-quality cinematic video with dramatic camera moves",
            "style_formula": (
                "Cinematic film quality. Camera: slow dolly-in or wide establishing shot. "
                "Lighting: dramatic, high contrast, golden/blue hour tones. "
                "Motion: smooth, intentional, no shaky cam. "
                "Mood: immersive, epic. Render: 4K, filmic color grade, depth of field. "
                "End every prompt with: photorealistic, 4K, smooth motion, --no text --no subtitles"
            ),
            "built_in": True,
        },
        {
            "id": "documentary_video",
            "name": "Documentary",
            "description": "Realistic handheld documentary style",
            "style_formula": (
                "Documentary-style footage. Camera: handheld, slightly unsteady, authentic. "
                "Lighting: natural, available light. "
                "Motion: realistic, observational. Mood: raw, authentic, journalistic. "
                "Render: 1080p, natural color, realistic grain. "
                "End every prompt with: documentary style, natural light, realistic, --no text --no subtitles"
            ),
            "built_in": True,
        },
        {
            "id": "animated_video",
            "name": "Animated",
            "description": "Clean 3D animated style with vibrant colors",
            "style_formula": (
                "3D animated style, Pixar/Disney quality. Camera: dynamic, expressive angles. "
                "Lighting: bright, warm, stylized. "
                "Motion: fluid, exaggerated, expressive. Mood: vibrant, energetic, playful. "
                "Render: 4K animation, vivid colors, smooth curves. "
                "End every prompt with: 3D animation, vibrant colors, smooth motion, --no text --no subtitles"
            ),
            "built_in": True,
        },
    ]

    @classmethod
    def _ensure_file(cls):
        cls.STYLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not cls.STYLES_FILE.exists():
            with open(cls.STYLES_FILE, 'w') as f:
                json.dump({"styles": []}, f, indent=2)

    @classmethod
    def _load_custom(cls) -> List[Dict]:
        cls._ensure_file()
        try:
            with open(cls.STYLES_FILE) as f:
                return json.load(f).get("styles", [])
        except Exception:
            return []

    @classmethod
    def _save_custom(cls, styles: List[Dict]):
        with open(cls.STYLES_FILE, 'w') as f:
            json.dump({"styles": styles}, f, indent=2)

    @classmethod
    def get_all(cls) -> List[Dict]:
        """Return built-in styles + custom styles."""
        return cls.BUILTIN_STYLES + cls._load_custom()

    @classmethod
    def get(cls, style_id: str) -> Optional[Dict]:
        return next((s for s in cls.get_all() if s['id'] == style_id), None)

    @classmethod
    def create(cls, name: str, style_formula: str, description: str = '') -> Dict:
        if not name or len(name.strip()) < 2:
            raise ValueError("Name must be at least 2 characters")
        if not style_formula or len(style_formula.strip()) < 10:
            raise ValueError("Style formula must be at least 10 characters")

        new = {
            "id": f"vid_{uuid.uuid4().hex[:8]}",
            "name": name.strip(),
            "description": description.strip(),
            "style_formula": style_formula.strip(),
            "built_in": False,
        }
        styles = cls._load_custom()
        styles.append(new)
        cls._save_custom(styles)
        return new

    @classmethod
    def update(cls, style_id: str, name: str = None, style_formula: str = None,
               description: str = None) -> Optional[Dict]:
        styles = cls._load_custom()
        idx = next((i for i, s in enumerate(styles) if s['id'] == style_id), None)
        if idx is None:
            return None
        if name is not None:
            styles[idx]['name'] = name.strip()
        if style_formula is not None:
            styles[idx]['style_formula'] = style_formula.strip()
        if description is not None:
            styles[idx]['description'] = description.strip()
        cls._save_custom(styles)
        return styles[idx]

    @classmethod
    def delete(cls, style_id: str) -> bool:
        styles = cls._load_custom()
        new_list = [s for s in styles if s['id'] != style_id]
        if len(new_list) == len(styles):
            return False
        cls._save_custom(new_list)
        return True

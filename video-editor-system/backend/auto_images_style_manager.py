"""
Auto Images Style Manager - CRUD for Director Gemini styles
Different from old 6-prompt system - uses style bibles for Director
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict, Optional


class AutoImagesStyleManager:
    """Manage styles for Auto Images AI (Director Gemini)"""

    STYLES_FILE = Path("data/auto_images_styles.json")

    # Default built-in styles
    DEFAULT_STYLES = [
        {
            "id": "cinematic",
            "name": "Cinematic",
            "description": "Cinematic film-quality visuals with dramatic lighting and composition",
            "visual_rules": [
                "Cinematic composition with rule of thirds",
                "Film-quality lighting and shadows",
                "Dramatic depth of field",
                "Professional color grading",
                "High production value aesthetic"
            ],
            "negative_rules": [
                "Low quality, blurry, distorted",
                "Amateur photography",
                "Flat lighting",
                "Poor composition"
            ],
            "composition": "Wide cinematic shots with professional framing, dramatic angles",
            "lighting": "Dramatic cinematic lighting with contrast and mood",
            "color_palette": ["Deep blues", "Rich golds", "Dramatic shadows", "Warm highlights"]
        },
        {
            "id": "photorealistic",
            "name": "Photorealistic",
            "description": "Ultra-realistic photography-style images",
            "visual_rules": [
                "Photorealistic details and textures",
                "Natural lighting and shadows",
                "Authentic camera perspective",
                "Real-world materials and surfaces",
                "Professional photography quality"
            ],
            "negative_rules": [
                "Cartoon, animated, illustrated",
                "Artificial or fake looking",
                "Oversaturated colors",
                "Unrealistic proportions"
            ],
            "composition": "Natural photography composition, authentic camera angles",
            "lighting": "Natural daylight or studio lighting, realistic shadows",
            "color_palette": ["Natural tones", "Realistic colors", "Authentic skin tones", "True-to-life hues"]
        },
        {
            "id": "artistic",
            "name": "Artistic",
            "description": "Creative artistic interpretation with painterly quality",
            "visual_rules": [
                "Artistic interpretation and style",
                "Painterly brushwork and textures",
                "Creative color choices",
                "Expressive composition",
                "Fine art aesthetic"
            ],
            "negative_rules": [
                "Photorealistic",
                "Generic or boring",
                "Overly technical",
                "Sterile composition"
            ],
            "composition": "Creative and expressive framing, artistic perspective",
            "lighting": "Dramatic artistic lighting, creative shadows and highlights",
            "color_palette": ["Bold colors", "Artistic contrasts", "Creative hues", "Expressive tones"]
        },
        {
            "id": "animated",
            "name": "Animated",
            "description": "Clean animated style with vibrant colors",
            "visual_rules": [
                "Clean 3D animation style",
                "Vibrant and appealing colors",
                "Smooth surfaces and textures",
                "Professional animation quality",
                "Stylized but polished look"
            ],
            "negative_rules": [
                "Photorealistic",
                "Rough or unfinished",
                "Muddy colors",
                "Low-quality rendering"
            ],
            "composition": "Clean animated framing, balanced and appealing",
            "lighting": "Bright and clear animated lighting, vibrant atmosphere",
            "color_palette": ["Vibrant colors", "Clean tones", "Bright highlights", "Rich saturation"]
        }
    ]

    @classmethod
    def _ensure_file_exists(cls):
        """Ensure styles file and directory exist"""
        cls.STYLES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not cls.STYLES_FILE.exists():
            # Initialize with default styles
            with open(cls.STYLES_FILE, 'w') as f:
                json.dump({"styles": cls.DEFAULT_STYLES}, f, indent=2)

    @classmethod
    def get_all_styles(cls) -> List[Dict]:
        """Get all styles (built-in + custom)"""
        cls._ensure_file_exists()
        try:
            with open(cls.STYLES_FILE, 'r') as f:
                data = json.load(f)
            return data.get("styles", cls.DEFAULT_STYLES)
        except Exception as e:
            print(f"Error loading styles: {e}")
            return cls.DEFAULT_STYLES

    @classmethod
    def get_style(cls, style_id: str) -> Optional[Dict]:
        """Get style by ID"""
        styles = cls.get_all_styles()
        return next((s for s in styles if s['id'] == style_id), None)

    @classmethod
    def create_style(
        cls,
        name: str,
        description: str = '',
        visual_rules: List[str] = None,
        negative_rules: List[str] = None,
        composition: str = '',
        lighting: str = '',
        color_palette: List[str] = None,
        style_formula: str = '',
    ) -> Dict:
        """Create new custom style.

        If style_formula is provided it is used as the complete style instruction
        and the structured fields become optional.
        """
        if not name or len(name.strip()) < 3:
            raise ValueError("Style name must be at least 3 characters")

        has_formula = bool(style_formula and style_formula.strip())

        if not has_formula:
            # Structured-fields mode — validate required fields
            if not visual_rules or len(visual_rules) < 3:
                raise ValueError("Provide at least 3 visual rules (or fill the Style Formula instead)")
            if not negative_rules or len(negative_rules) < 2:
                raise ValueError("Provide at least 2 negative rules (or fill the Style Formula instead)")
            if not composition or len(composition.strip()) < 5:
                raise ValueError("Composition is required when Style Formula is empty")
            if not lighting or len(lighting.strip()) < 5:
                raise ValueError("Lighting is required when Style Formula is empty")
            if not color_palette or len(color_palette) < 3:
                raise ValueError("Provide at least 3 colors (or fill the Style Formula instead)")

        style_id = f"custom_{uuid.uuid4().hex[:8]}"

        new_style = {
            "id": style_id,
            "name": name.strip(),
            "description": (description or '').strip(),
            "style_formula": style_formula.strip() if has_formula else '',
            "visual_rules": [r.strip() for r in (visual_rules or [])],
            "negative_rules": [r.strip() for r in (negative_rules or [])],
            "composition": (composition or '').strip(),
            "lighting": (lighting or '').strip(),
            "color_palette": [c.strip() for c in (color_palette or [])],
            "custom": True
        }

        # Load existing styles
        cls._ensure_file_exists()
        try:
            with open(cls.STYLES_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {"styles": cls.DEFAULT_STYLES}

        # Add new style
        data["styles"].append(new_style)

        # Save
        with open(cls.STYLES_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return new_style

    @classmethod
    def update_style(
        cls,
        style_id: str,
        name: str = None,
        description: str = None,
        visual_rules: List[str] = None,
        negative_rules: List[str] = None,
        composition: str = None,
        lighting: str = None,
        color_palette: List[str] = None,
        style_formula: str = None,
    ) -> Optional[Dict]:
        """
        Update existing style

        Args:
            style_id: Style ID to update
            (other args): Updated values (optional)

        Returns:
            Updated style or None if not found or not custom
        """
        cls._ensure_file_exists()

        try:
            with open(cls.STYLES_FILE, 'r') as f:
                data = json.load(f)
        except:
            return None

        styles = data.get("styles", [])
        style_index = next((i for i, s in enumerate(styles) if s['id'] == style_id), None)

        if style_index is None:
            return None

        style = styles[style_index]

        # Can only update custom styles
        if not style.get("custom", False):
            raise ValueError("Cannot update built-in styles")

        # Update fields
        if name is not None:
            if len(name.strip()) < 3:
                raise ValueError("Name must be at least 3 characters")
            style["name"] = name.strip()

        if description is not None:
            if len(description.strip()) < 10:
                raise ValueError("Description must be at least 10 characters")
            style["description"] = description.strip()

        if visual_rules is not None:
            if len(visual_rules) < 3:
                raise ValueError("Must provide at least 3 visual rules")
            style["visual_rules"] = [r.strip() for r in visual_rules]

        if negative_rules is not None:
            if len(negative_rules) < 2:
                raise ValueError("Must provide at least 2 negative rules")
            style["negative_rules"] = [r.strip() for r in negative_rules]

        if composition is not None:
            if len(composition.strip()) < 10:
                raise ValueError("Composition must be at least 10 characters")
            style["composition"] = composition.strip()

        if lighting is not None:
            if len(lighting.strip()) < 10:
                raise ValueError("Lighting must be at least 10 characters")
            style["lighting"] = lighting.strip()

        if color_palette is not None:
            style["color_palette"] = [c.strip() for c in color_palette]

        if style_formula is not None:
            style["style_formula"] = style_formula.strip()

        # Save
        with open(cls.STYLES_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return style

    @classmethod
    def delete_style(cls, style_id: str) -> bool:
        """
        Delete custom style

        Args:
            style_id: Style ID to delete

        Returns:
            True if deleted, False if not found or not custom
        """
        cls._ensure_file_exists()

        try:
            with open(cls.STYLES_FILE, 'r') as f:
                data = json.load(f)
        except:
            return False

        styles = data.get("styles", [])
        style_index = next((i for i, s in enumerate(styles) if s['id'] == style_id), None)

        if style_index is None:
            return False

        style = styles[style_index]

        # Can only delete custom styles
        if not style.get("custom", False):
            raise ValueError("Cannot delete built-in styles")

        # Remove style
        styles.pop(style_index)

        # Save
        with open(cls.STYLES_FILE, 'w') as f:
            json.dump({"styles": styles}, f, indent=2)

        return True

"""
Pydantic schemas for Auto Images AI system
Strict JSON validation for Gemini Director output
"""

from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import List, Optional, Literal


class SceneCard(BaseModel):
    """Single scene with image prompt"""
    scene_id: int = Field(..., description="Scene number (1-indexed)")
    scene_summary: str = Field(..., min_length=10, description="Brief scene description")
    narration_focus: str = Field(..., min_length=5, description="What the narration talks about")
    keywords: List[str] = Field(..., min_items=3, max_items=10, description="Key visual elements")
    image_prompt: str = Field(..., min_length=50, description="Detailed image generation prompt")
    negative_prompt: str = Field(..., description="What to avoid in the image")

    @field_validator('keywords', mode='before')
    @classmethod
    def trim_keywords(cls, v):
        """Auto-trim to 10 items when LLM returns too many — avoids validation error."""
        if isinstance(v, list) and len(v) > 10:
            return v[:10]
        return v

    @field_validator('image_prompt')
    @classmethod
    def validate_prompt_quality(cls, v):
        """Ensure prompt has required components"""
        # Prompt must be extremely detailed: 300+ characters minimum
        char_count = len(v)
        if char_count < 300:
            raise ValueError(f'Prompt too short: {char_count} characters (minimum 300 characters for quality)')
        if char_count > 2000:
            raise ValueError(f'Prompt too long: {char_count} characters (maximum 2000 characters)')
        return v


class GlobalStyleBible(BaseModel):
    """Global style rules applied to all images"""
    style_name: str = Field(..., description="Name of the visual style")
    visual_rules: List[str] = Field(..., min_items=3, description="Visual guidelines to follow")
    negative_rules: List[str] = Field(..., min_items=2, description="Things to avoid")
    composition: str = Field(..., description="Overall composition approach")
    lighting: str = Field(..., description="Lighting style")
    color_palette: List[str] = Field(..., min_items=3, max_items=10, description="Color scheme")

    @field_validator('color_palette', mode='before')
    @classmethod
    def trim_color_palette(cls, v):
        """Auto-trim to 10 items when LLM returns too many."""
        if isinstance(v, list) and len(v) > 10:
            return v[:10]
        return v


class AutoImagesPlan(BaseModel):
    """Complete plan for auto-generated images"""
    mode: Literal["auto_images"] = "auto_images"
    style_id: str = Field(..., description="ID of the style used")
    n_images: int = Field(..., ge=1, le=100, description="Number of images to generate")
    global_style_bible: GlobalStyleBible
    scenes: List[SceneCard] = Field(..., description="List of scene cards (must equal n_images)")

    @field_validator('scenes')
    @classmethod
    def validate_scene_count(cls, v, info: ValidationInfo):
        """Ensure number of scenes matches n_images"""
        if info.data and 'n_images' in info.data and len(v) != info.data['n_images']:
            raise ValueError(f"Expected {info.data['n_images']} scenes, got {len(v)}")

        # Also validate scene IDs are sequential
        expected_ids = list(range(1, len(v) + 1))
        actual_ids = [scene.scene_id for scene in v]
        if actual_ids != expected_ids:
            raise ValueError(f"Scene IDs must be sequential 1..{len(v)}, got {actual_ids}")

        return v


class ImageItem(BaseModel):
    """Single image in the timeline"""
    id: str = Field(..., description="Unique ID")
    source_type: str = Field(..., description="'generated', 'local', or 'stock'")
    path: str = Field(..., description="Path to image file")
    scene_id: Optional[int] = Field(None, description="Scene ID if generated")
    prompt_used: Optional[str] = Field(None, description="Prompt used if generated")
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None


class TimelineState(BaseModel):
    """Editable timeline of images"""
    style_id: str
    script_hash: str = Field(..., description="Hash of the script used")
    director_version: str = Field(default="v1", description="Director prompt version")
    items: List[ImageItem] = Field(default_factory=list, description="Ordered list of images")

    def add_local_image(self, path: str, index: Optional[int] = None):
        """Add a local image at specified index (or end)"""
        import uuid
        item = ImageItem(
            id=str(uuid.uuid4()),
            source_type="local",
            path=path
        )
        if index is None:
            self.items.append(item)
        else:
            self.items.insert(index, item)

    def add_stock_image(self, path: str, index: Optional[int] = None):
        """Add a stock image at specified index (or end)"""
        import uuid
        item = ImageItem(
            id=str(uuid.uuid4()),
            source_type="stock",
            path=path
        )
        if index is None:
            self.items.append(item)
        else:
            self.items.insert(index, item)

    def delete(self, index: int):
        """Delete image at index"""
        if 0 <= index < len(self.items):
            self.items.pop(index)

    def move(self, old_index: int, new_index: int):
        """Move image from old_index to new_index"""
        if 0 <= old_index < len(self.items) and 0 <= new_index < len(self.items):
            item = self.items.pop(old_index)
            self.items.insert(new_index, item)

    def replace_generated(self, scene_id: int, new_path: str):
        """Replace a generated image with new path"""
        for item in self.items:
            if item.scene_id == scene_id:
                item.path = new_path
                break

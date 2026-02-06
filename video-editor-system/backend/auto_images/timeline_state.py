"""
Timeline state management for Auto Images
Handles loading, saving, and editing the image timeline
"""

import json
import hashlib
from pathlib import Path
from typing import List, Optional

from .schema import TimelineState, ImageItem


class TimelineManager:
    """Manage timeline state for auto-generated images"""

    TIMELINE_FILE = Path("output/auto_images_timeline.json")

    def __init__(self):
        """Initialize timeline manager"""
        self.TIMELINE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _compute_script_hash(self, script_text: str) -> str:
        """Compute hash of script for change detection"""
        return hashlib.sha256(script_text.encode()).hexdigest()[:16]

    def create_timeline(
        self,
        items: List[ImageItem],
        style_id: str,
        script_text: str,
        director_version: str = "v1"
    ) -> TimelineState:
        """
        Create new timeline from generated images

        Args:
            items: List of ImageItem from generation
            style_id: Style ID used
            script_text: Script text (for hash)
            director_version: Director version

        Returns:
            TimelineState
        """
        script_hash = self._compute_script_hash(script_text)

        timeline = TimelineState(
            style_id=style_id,
            script_hash=script_hash,
            director_version=director_version,
            items=items
        )

        return timeline

    def save_timeline(self, timeline: TimelineState) -> Path:
        """
        Save timeline to JSON file

        Args:
            timeline: TimelineState to save

        Returns:
            Path to saved file
        """
        with open(self.TIMELINE_FILE, 'w') as f:
            json.dump(timeline.dict(), f, indent=2)

        return self.TIMELINE_FILE

    def load_timeline(self) -> Optional[TimelineState]:
        """
        Load timeline from JSON file

        Returns:
            TimelineState or None if not exists
        """
        if not self.TIMELINE_FILE.exists():
            return None

        try:
            with open(self.TIMELINE_FILE, 'r') as f:
                data = json.load(f)
            return TimelineState(**data)
        except Exception as e:
            print(f"Failed to load timeline: {e}")
            return None

    def add_local_image(
        self,
        timeline: TimelineState,
        image_path: str,
        index: Optional[int] = None
    ) -> TimelineState:
        """
        Add a local image to timeline

        Args:
            timeline: Current timeline
            image_path: Path to local image
            index: Position to insert (None = end)

        Returns:
            Updated timeline
        """
        timeline.add_local_image(image_path, index)
        self.save_timeline(timeline)
        return timeline

    def add_stock_image(
        self,
        timeline: TimelineState,
        image_path: str,
        index: Optional[int] = None
    ) -> TimelineState:
        """
        Add a stock image to timeline

        Args:
            timeline: Current timeline
            image_path: Path to stock image
            index: Position to insert (None = end)

        Returns:
            Updated timeline
        """
        timeline.add_stock_image(image_path, index)
        self.save_timeline(timeline)
        return timeline

    def delete_image(
        self,
        timeline: TimelineState,
        index: int
    ) -> TimelineState:
        """
        Delete image from timeline

        Args:
            timeline: Current timeline
            index: Index to delete

        Returns:
            Updated timeline
        """
        timeline.delete(index)
        self.save_timeline(timeline)
        return timeline

    def move_image(
        self,
        timeline: TimelineState,
        old_index: int,
        new_index: int
    ) -> TimelineState:
        """
        Move image in timeline

        Args:
            timeline: Current timeline
            old_index: Current position
            new_index: Target position

        Returns:
            Updated timeline
        """
        timeline.move(old_index, new_index)
        self.save_timeline(timeline)
        return timeline

    def replace_generated_image(
        self,
        timeline: TimelineState,
        scene_id: int,
        new_path: str
    ) -> TimelineState:
        """
        Replace a generated image with new version

        Args:
            timeline: Current timeline
            scene_id: Scene ID to replace
            new_path: New image path

        Returns:
            Updated timeline
        """
        timeline.replace_generated(scene_id, new_path)
        self.save_timeline(timeline)
        return timeline

    def clear_timeline(self) -> bool:
        """
        Delete timeline file

        Returns:
            True if deleted, False if not exists
        """
        if self.TIMELINE_FILE.exists():
            self.TIMELINE_FILE.unlink()
            return True
        return False

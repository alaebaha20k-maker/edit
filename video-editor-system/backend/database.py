#!/usr/bin/env python3
"""
JSON-based database for AI Video Generator
Stores niches, image styles, and generated videos
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from config import Config


class Database:
    """Simple JSON-based database"""

    @staticmethod
    def _read_json(file_path: Path) -> List[Dict]:
        """Read JSON file, return empty list if doesn't exist"""
        if not file_path.exists():
            return []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"⚠️  Warning: Corrupted JSON file {file_path}, returning empty list")
            return []

    @staticmethod
    def _write_json(file_path: Path, data: List[Dict]):
        """Write data to JSON file"""
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _generate_id() -> str:
        """Generate unique ID"""
        return str(uuid.uuid4())

    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format"""
        return datetime.utcnow().isoformat()


class NicheDatabase(Database):
    """Database operations for niches"""

    @classmethod
    def get_all(cls) -> List[Dict]:
        """Get all niches"""
        return cls._read_json(Config.NICHES_DB)

    @classmethod
    def get_by_id(cls, niche_id: str) -> Optional[Dict]:
        """Get niche by ID"""
        niches = cls.get_all()
        for niche in niches:
            if niche.get('id') == niche_id:
                return niche
        return None

    @classmethod
    def create(cls, name: str, language: str, writing_guidelines: str) -> Dict:
        """Create new niche"""
        niches = cls.get_all()

        niche = {
            'id': cls._generate_id(),
            'name': name,
            'language': language,
            'writing_guidelines': writing_guidelines,
            'created_at': cls._get_timestamp(),
            'updated_at': cls._get_timestamp()
        }

        niches.append(niche)
        cls._write_json(Config.NICHES_DB, niches)

        return niche

    @classmethod
    def update(cls, niche_id: str, name: str = None, language: str = None,
               writing_guidelines: str = None) -> Optional[Dict]:
        """Update existing niche"""
        niches = cls.get_all()

        for i, niche in enumerate(niches):
            if niche.get('id') == niche_id:
                if name is not None:
                    niche['name'] = name
                if language is not None:
                    niche['language'] = language
                if writing_guidelines is not None:
                    niche['writing_guidelines'] = writing_guidelines

                niche['updated_at'] = cls._get_timestamp()
                niches[i] = niche

                cls._write_json(Config.NICHES_DB, niches)
                return niche

        return None

    @classmethod
    def delete(cls, niche_id: str) -> bool:
        """Delete niche"""
        niches = cls.get_all()
        original_count = len(niches)

        niches = [n for n in niches if n.get('id') != niche_id]

        if len(niches) < original_count:
            cls._write_json(Config.NICHES_DB, niches)
            return True

        return False


class ImageStyleDatabase(Database):
    """Database operations for image styles"""

    @classmethod
    def get_all(cls) -> List[Dict]:
        """Get all image styles"""
        return cls._read_json(Config.IMAGE_STYLES_DB)

    @classmethod
    def get_by_id(cls, style_id: str) -> Optional[Dict]:
        """Get image style by ID"""
        styles = cls.get_all()
        for style in styles:
            if style.get('id') == style_id:
                return style
        return None

    @classmethod
    def create(cls, name: str, prompts: List[str]) -> Dict:
        """Create new image style"""
        if len(prompts) != 6:
            raise ValueError("Image style must have exactly 6 prompts")

        styles = cls.get_all()

        style = {
            'id': cls._generate_id(),
            'name': name,
            'prompts': prompts,
            'created_at': cls._get_timestamp(),
            'updated_at': cls._get_timestamp()
        }

        styles.append(style)
        cls._write_json(Config.IMAGE_STYLES_DB, styles)

        return style

    @classmethod
    def update(cls, style_id: str, name: str = None, prompts: List[str] = None) -> Optional[Dict]:
        """Update existing image style"""
        if prompts is not None and len(prompts) != 6:
            raise ValueError("Image style must have exactly 6 prompts")

        styles = cls.get_all()

        for i, style in enumerate(styles):
            if style.get('id') == style_id:
                if name is not None:
                    style['name'] = name
                if prompts is not None:
                    style['prompts'] = prompts

                style['updated_at'] = cls._get_timestamp()
                styles[i] = style

                cls._write_json(Config.IMAGE_STYLES_DB, styles)
                return style

        return None

    @classmethod
    def delete(cls, style_id: str) -> bool:
        """Delete image style"""
        styles = cls.get_all()
        original_count = len(styles)

        styles = [s for s in styles if s.get('id') != style_id]

        if len(styles) < original_count:
            cls._write_json(Config.IMAGE_STYLES_DB, styles)
            return True

        return False


class VideoDatabase(Database):
    """Database operations for generated videos"""

    @classmethod
    def get_all(cls) -> List[Dict]:
        """Get all videos"""
        return cls._read_json(Config.VIDEOS_DB)

    @classmethod
    def get_recent(cls, limit: int = 10) -> List[Dict]:
        """Get recent videos"""
        videos = cls.get_all()
        # Sort by created_at descending
        videos.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return videos[:limit]

    @classmethod
    def get_by_id(cls, video_id: str) -> Optional[Dict]:
        """Get video by ID"""
        videos = cls.get_all()
        for video in videos:
            if video.get('id') == video_id:
                return video
        return None

    @classmethod
    def create(cls, title: str, niche_id: str, style_id: str, script: str,
               image_urls: List[str], audio_paths: List[str], output_path: str) -> Dict:
        """Create new video record"""
        videos = cls.get_all()

        video = {
            'id': cls._generate_id(),
            'title': title,
            'niche_id': niche_id,
            'style_id': style_id,
            'script': script,
            'image_urls': image_urls,
            'audio_paths': audio_paths,
            'output_path': output_path,
            'created_at': cls._get_timestamp()
        }

        videos.append(video)
        cls._write_json(Config.VIDEOS_DB, videos)

        return video


if __name__ == "__main__":
    # Test database operations
    print("Testing database operations...")

    # Test niche creation
    niche = NicheDatabase.create(
        name="Trading Psychology",
        language="English",
        writing_guidelines="Write about trading psychology and mindset..."
    )
    print(f"✓ Created niche: {niche['name']}")

    # Test image style creation
    style = ImageStyleDatabase.create(
        name="Stick Figure Trading",
        prompts=[
            "Minimalist stick figure trader at desk {TITLE_KEYWORDS}",
            "Simple stick figure showing {EMOTIONAL_STATE}",
            "Basic stick figure looking at chart {CHART_PATTERN}",
            "Clean stick figure celebrating trading win",
            "Stick figure analyzing market data",
            "Stick figure with zen mindset trading"
        ]
    )
    print(f"✓ Created image style: {style['name']}")

    print("\nAll database tests passed!")

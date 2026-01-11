#!/usr/bin/env python3
"""
Settings Manager for AI Video Generator
Handles API keys, generation formulas, and voice configurations
"""

import json
from pathlib import Path
from typing import Dict, Optional

class SettingsManager:
    """Manages system settings, API keys, and generation formulas"""

    # Paths
    BASE_DIR = Path(__file__).parent.parent.resolve()
    DATA_DIR = BASE_DIR / 'data'
    SETTINGS_FILE = DATA_DIR / 'settings.json'

    # Formula files
    FORMULAS_DIR = DATA_DIR / 'formulas'
    TITLE_FORMULA_FILE = FORMULAS_DIR / 'title_formula.txt'
    SCRIPT_FORMULA_FILE = FORMULAS_DIR / 'script_formula.txt'
    IMAGE_FORMULA_FILE = FORMULAS_DIR / 'image_formula.txt'

    # Default formulas
    DEFAULT_TITLE_FORMULA = """Create an engaging video title about: {topic}

Requirements:
- Attention-grabbing and clickable
- 50-70 characters max
- Include numbers or power words when relevant
- Match the tone of the content

Output ONLY the title, no quotes or extra text."""

    DEFAULT_SCRIPT_FORMULA = """Write a comprehensive video script about: {topic}

Target length: {target_length} characters (~{word_count} words)

Structure:
1. Hook (first 30 seconds - grab attention)
2. Introduction (set context and promise value)
3. Main content (detailed exploration with examples)
4. Conclusion (summarize and call-to-action)

Style:
- Conversational and engaging tone
- Use storytelling and examples
- Transition smoothly between sections
- End sentences with natural pauses for voice-over

Format:
- Plain text only (no markdown, asterisks, or special formatting)
- No timestamps or speaker labels
- Natural spoken language
- Ready for text-to-speech

Output ONLY the script content."""

    DEFAULT_IMAGE_FORMULA = """Generate {count} detailed image prompts for a video about: {topic}

Each prompt should:
- Be visually distinct and relevant to the topic
- Include style: {style}
- Be 1-2 sentences, descriptive and specific
- Work well with AI image generation (Flux/Stable Diffusion)

Output format (JSON array):
[
  "prompt 1 description",
  "prompt 2 description",
  ...
]

Output ONLY the JSON array, no extra text."""

    # Inworld AI voice configurations
    INWORLD_VOICES = {
        # English voices
        'dennis': {
            'name': 'Dennis',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Deep, authoritative voice - great for documentaries',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/dennis_preview.mp3'
        },
        'marcus': {
            'name': 'Marcus',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Friendly, conversational - perfect for tutorials',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/marcus_preview.mp3'
        },
        'brandon': {
            'name': 'Brandon',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Energetic, young voice - ideal for entertainment',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/brandon_preview.mp3'
        },
        'ava': {
            'name': 'Ava',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Professional, clear - great for educational content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/ava_preview.mp3'
        },
        'emma': {
            'name': 'Emma',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Warm, engaging - perfect for storytelling',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/emma_preview.mp3'
        },
        # French voices
        'jean-fr': {
            'name': 'Jean',
            'language': 'fr-FR',
            'gender': 'Male',
            'description': 'Voix masculine professionnelle française',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/jean_preview.mp3'
        },
        'marie-fr': {
            'name': 'Marie',
            'language': 'fr-FR',
            'gender': 'Female',
            'description': 'Voix féminine chaleureuse française',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/marie_preview.mp3'
        }
    }

    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.FORMULAS_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load_settings(cls) -> Dict:
        """Load all settings from file"""
        cls.ensure_directories()

        if cls.SETTINGS_FILE.exists():
            try:
                with open(cls.SETTINGS_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading settings: {e}")
                return cls._get_default_settings()

        return cls._get_default_settings()

    @classmethod
    def _get_default_settings(cls) -> Dict:
        """Get default settings structure"""
        return {
            'api_keys': {
                'gemini': '',
                'replicate': '',
                'inworld': '',
                'pexels': ''
            },
            'voice_settings': {
                'default_voice': 'marcus',
                'speaking_rate': 1.0
            }
        }

    @classmethod
    def save_api_keys(cls, gemini: str = None, replicate: str = None,
                     inworld: str = None, pexels: str = None) -> Dict:
        """
        Save API keys to settings file

        Args:
            gemini: Gemini API key
            replicate: Replicate API token
            inworld: Inworld AI API key (base64 credential)
            pexels: Pexels API key

        Returns:
            Updated settings dictionary
        """
        cls.ensure_directories()
        settings = cls.load_settings()

        # Update only provided keys
        if gemini is not None:
            settings['api_keys']['gemini'] = gemini
        if replicate is not None:
            settings['api_keys']['replicate'] = replicate
        if inworld is not None:
            settings['api_keys']['inworld'] = inworld
        if pexels is not None:
            settings['api_keys']['pexels'] = pexels

        # Save to file
        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)

        return settings

    @classmethod
    def get_api_key(cls, key_name: str) -> str:
        """
        Get a specific API key

        Args:
            key_name: One of 'gemini', 'replicate', 'inworld', 'pexels'

        Returns:
            API key string (empty if not set)
        """
        settings = cls.load_settings()
        return settings.get('api_keys', {}).get(key_name, '')

    @classmethod
    def save_formulas(cls, title_formula: str = None, script_formula: str = None,
                     image_formula: str = None) -> bool:
        """
        Save generation formulas to text files

        Args:
            title_formula: Template for title generation
            script_formula: Template for script generation
            image_formula: Template for image prompt generation

        Returns:
            True if successful
        """
        cls.ensure_directories()

        try:
            if title_formula is not None:
                with open(cls.TITLE_FORMULA_FILE, 'w') as f:
                    f.write(title_formula)

            if script_formula is not None:
                with open(cls.SCRIPT_FORMULA_FILE, 'w') as f:
                    f.write(script_formula)

            if image_formula is not None:
                with open(cls.IMAGE_FORMULA_FILE, 'w') as f:
                    f.write(image_formula)

            return True
        except Exception as e:
            print(f"Error saving formulas: {e}")
            return False

    @classmethod
    def load_formula(cls, formula_type: str) -> str:
        """
        Load a specific formula

        Args:
            formula_type: One of 'title', 'script', 'image'

        Returns:
            Formula text (default formula if file doesn't exist)
        """
        cls.ensure_directories()

        formula_map = {
            'title': (cls.TITLE_FORMULA_FILE, cls.DEFAULT_TITLE_FORMULA),
            'script': (cls.SCRIPT_FORMULA_FILE, cls.DEFAULT_SCRIPT_FORMULA),
            'image': (cls.IMAGE_FORMULA_FILE, cls.DEFAULT_IMAGE_FORMULA)
        }

        if formula_type not in formula_map:
            raise ValueError(f"Invalid formula type: {formula_type}")

        file_path, default_formula = formula_map[formula_type]

        if file_path.exists():
            try:
                with open(file_path, 'r') as f:
                    return f.read()
            except Exception as e:
                print(f"Error loading {formula_type} formula: {e}")
                return default_formula

        # Return default and save it for next time
        cls.save_formulas(**{f'{formula_type}_formula': default_formula})
        return default_formula

    @classmethod
    def save_voice_settings(cls, default_voice: str = None,
                           speaking_rate: float = None) -> Dict:
        """
        Save voice settings

        Args:
            default_voice: Voice ID (e.g., 'marcus', 'ava')
            speaking_rate: Speed multiplier (0.8 - 1.5)

        Returns:
            Updated settings dictionary
        """
        cls.ensure_directories()
        settings = cls.load_settings()

        if 'voice_settings' not in settings:
            settings['voice_settings'] = {}

        if default_voice is not None:
            if default_voice not in cls.INWORLD_VOICES:
                raise ValueError(f"Invalid voice ID: {default_voice}")
            settings['voice_settings']['default_voice'] = default_voice

        if speaking_rate is not None:
            if not 0.8 <= speaking_rate <= 1.5:
                raise ValueError("Speaking rate must be between 0.8 and 1.5")
            settings['voice_settings']['speaking_rate'] = speaking_rate

        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)

        return settings

    @classmethod
    def get_voice_settings(cls) -> Dict:
        """Get current voice settings"""
        settings = cls.load_settings()
        return settings.get('voice_settings', {
            'default_voice': 'marcus',
            'speaking_rate': 1.0
        })

    @classmethod
    def get_all_voices(cls) -> Dict:
        """Get all available Inworld AI voices"""
        return cls.INWORLD_VOICES

    @classmethod
    def validate_api_keys(cls) -> Dict:
        """
        Validate that required API keys are set

        Returns:
            Dictionary with status for each key
        """
        settings = cls.load_settings()
        api_keys = settings.get('api_keys', {})

        return {
            'gemini': {
                'configured': bool(api_keys.get('gemini')),
                'required': True
            },
            'replicate': {
                'configured': bool(api_keys.get('replicate')),
                'required': True
            },
            'inworld': {
                'configured': bool(api_keys.get('inworld')),
                'required': False  # Optional for now
            },
            'pexels': {
                'configured': bool(api_keys.get('pexels')),
                'required': False  # Optional for now
            }
        }

    @classmethod
    def get_settings_summary(cls) -> Dict:
        """Get a summary of all settings for display"""
        settings = cls.load_settings()
        api_validation = cls.validate_api_keys()

        return {
            'api_keys': {
                key: {
                    'configured': api_validation[key]['configured'],
                    'value': '***' if settings['api_keys'].get(key) else ''
                }
                for key in ['gemini', 'replicate', 'inworld', 'pexels']
            },
            'formulas': {
                'title': len(cls.load_formula('title')),
                'script': len(cls.load_formula('script')),
                'image': len(cls.load_formula('image'))
            },
            'voice_settings': cls.get_voice_settings(),
            'available_voices': len(cls.INWORLD_VOICES)
        }


# Initialize directories on import
SettingsManager.ensure_directories()

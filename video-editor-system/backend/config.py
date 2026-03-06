#!/usr/bin/env python3
"""
Configuration management for AI Video Generator
Handles API keys and system settings
"""

import os
import json
from pathlib import Path

class Config:
    """Configuration manager for API keys and paths"""

    # Paths (define first so we can use them)
    BASE_DIR = Path(__file__).parent.parent.resolve()
    BACKEND_DIR = BASE_DIR / 'backend'
    DATA_DIR = BASE_DIR / 'data'
    UPLOADS_DIR = BASE_DIR / 'uploads'
    OUTPUT_DIR = BASE_DIR / 'output'
    TEMP_DIR = BASE_DIR / 'temp'

    # API Config file
    API_CONFIG_FILE = DATA_DIR / 'api_config.json'

    # API Keys - read from saved config file, fallback to environment variables
    _saved_config = None

    @classmethod
    def _load_saved_config(cls):
        """Load API keys from saved config file"""
        if cls._saved_config is not None:
            return cls._saved_config

        if cls.API_CONFIG_FILE.exists():
            try:
                with open(cls.API_CONFIG_FILE, 'r') as f:
                    cls._saved_config = json.load(f)
                    return cls._saved_config
            except:
                pass

        cls._saved_config = {}
        return cls._saved_config

    @classmethod
    def get_gemini_api_key(cls):
        """Get Gemini API key (for script writing) from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('gemini_api_key') or os.getenv('GEMINI_API_KEY', '')

    @classmethod
    def get_director_gemini_api_key(cls):
        """
        Get Director Gemini API key (SEPARATE from script writer!)
        Used ONLY for Auto Images AI Director
        """
        saved = cls._load_saved_config()
        # Use separate key if available, otherwise fallback to main Gemini key
        return saved.get('director_gemini_api_key') or saved.get('gemini_api_key') or os.getenv('DIRECTOR_GEMINI_API_KEY') or os.getenv('GEMINI_API_KEY', '')

    @classmethod
    def get_gemini_image_api_key(cls):
        """
        Get Gemini Image API key for image generation (Gemini 2.5 Flash Image).
        Falls back to director key, then main Gemini key.
        """
        saved = cls._load_saved_config()
        return (
            saved.get('gemini_image_api_key')
            or os.getenv('GEMINI_IMAGE_API_KEY', '')
            or saved.get('director_gemini_api_key')
            or saved.get('gemini_api_key')
            or os.getenv('GEMINI_API_KEY', '')
        )

    @classmethod
    def get_director_gemini_model(cls):
        """Get Director Gemini model name (same as script generator)"""
        saved = cls._load_saved_config()
        return saved.get('director_gemini_model', 'gemini-2.5-flash')

    @classmethod
    def get_replicate_api_token(cls):
        """Get Replicate API token from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('replicate_api_token') or os.getenv('REPLICATE_API_TOKEN', '')

    @classmethod
    def get_inworld_api_key(cls):
        """Get Inworld API Key from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('inworld_api_key') or os.getenv('INWORLD_API_KEY', '')

    @classmethod
    def get_inworld_api_secret(cls):
        """Get Inworld API Secret from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('inworld_api_secret') or os.getenv('INWORLD_API_SECRET', '')

    @classmethod
    def get_gemini_translate_1_key(cls):
        """Get Gemini Translation API Key 1 (for parallel script translation)"""
        saved = cls._load_saved_config()
        return saved.get('gemini_translate_1') or os.getenv('GEMINI_TRANSLATE_1', '')

    @classmethod
    def get_gemini_translate_2_key(cls):
        """Get Gemini Translation API Key 2 (for parallel script translation)"""
        saved = cls._load_saved_config()
        return saved.get('gemini_translate_2') or os.getenv('GEMINI_TRANSLATE_2', '')

    # For backward compatibility, make them accessible as class attributes
    GEMINI_API_KEY = property(lambda self: self.get_gemini_api_key())
    REPLICATE_API_TOKEN = property(lambda self: self.get_replicate_api_token())

    @classmethod
    def save_api_config(cls, gemini_key=None, director_gemini_key=None, gemini_image_key=None, replicate_token=None, inworld_key=None, inworld_secret=None, gemini_translate_1=None, gemini_translate_2=None):
        """Save API keys to config file"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Load existing config
        config = {}
        if cls.API_CONFIG_FILE.exists():
            try:
                with open(cls.API_CONFIG_FILE, 'r') as f:
                    config = json.load(f)
            except:
                pass

        # Update keys (only if provided)
        if gemini_key:
            config['gemini_api_key'] = gemini_key
        if director_gemini_key:
            config['director_gemini_api_key'] = director_gemini_key
        if gemini_image_key:
            config['gemini_image_api_key'] = gemini_image_key
        if replicate_token:
            config['replicate_api_token'] = replicate_token
        if inworld_key:
            config['inworld_api_key'] = inworld_key
        if inworld_secret:
            config['inworld_api_secret'] = inworld_secret
        if gemini_translate_1:
            config['gemini_translate_1'] = gemini_translate_1
        if gemini_translate_2:
            config['gemini_translate_2'] = gemini_translate_2

        # Save to file
        with open(cls.API_CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)

        # Clear cache so next access reloads
        cls._saved_config = None

    @classmethod
    def clear_api_config(cls):
        """Clear all saved API keys"""
        if cls.API_CONFIG_FILE.exists():
            cls.API_CONFIG_FILE.unlink()
        cls._saved_config = None

    @classmethod
    def get_api_config_status(cls):
        """Get status of API configuration"""
        return {
            'gemini_configured': bool(cls.get_gemini_api_key()),
            'replicate_configured': bool(cls.get_replicate_api_token()),
            'inworld_configured': bool(cls.get_inworld_api_key() and cls.get_inworld_api_secret()),
            'config_file_exists': cls.API_CONFIG_FILE.exists()
        }

    # Gemini Settings - EXACT from HTML reference
    GEMINI_MODEL = 'gemini-2.5-flash'
    GEMINI_MAX_TOKENS = 65536  # EXACT from HTML
    GEMINI_TOP_P = 0.92  # EXACT from HTML
    GEMINI_TOP_K = 35  # EXACT from HTML
    # Temperature varies by part: 0.90 (part 1), 0.85 (part 2), 0.80 (part 3)
    GEMINI_TEMPERATURE_PART1 = 0.90
    GEMINI_TEMPERATURE_PART2 = 0.85
    GEMINI_TEMPERATURE_PART3 = 0.80

    # Replicate Settings
    REPLICATE_MODEL = 'black-forest-labs/flux-schnell'
    REPLICATE_COST_PER_IMAGE = 0.003

    # Database files
    NICHES_DB = DATA_DIR / 'niches.json'
    IMAGE_STYLES_DB = DATA_DIR / 'image_styles.json'
    VIDEOS_DB = DATA_DIR / 'videos.json'

    # Image generation settings
    IMAGES_PER_VIDEO = 6
    IMAGE_DURATION_SECONDS = 5.0  # Duration for each image in video

    # Script generation settings - FULL RANGE SUPPORT
    # Allow any length from 1,000 to 80,000 characters
    MIN_SCRIPT_LENGTH = 1000      # Minimum: ~1 min video (Shorts)
    MAX_SCRIPT_LENGTH = 80000     # Maximum: ~60+ min video (Documentary)
    DEFAULT_SCRIPT_LENGTH = 10000 # Default: ~10-12 min video

    # Valid discrete script lengths (used by generate_script() 3-part generator)
    VALID_SCRIPT_LENGTHS = [30000, 60000, 100000]

    # Length tolerance for validation (±3%)
    SCRIPT_LENGTH_TOLERANCE = 0.03

    # Maximum regeneration attempts when validation fails
    MAX_SCRIPT_RETRIES = 3

    @classmethod
    def ensure_directories(cls):
        """Create necessary directories if they don't exist"""
        directories = [
            cls.DATA_DIR,
            cls.UPLOADS_DIR,
            cls.OUTPUT_DIR,
            cls.TEMP_DIR
        ]

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def validate_api_keys(cls):
        """Validate that required API keys are set"""
        errors = []

        if not cls.get_gemini_api_key():
            errors.append("GEMINI_API_KEY not set. Configure via web UI at /api-config.html or set environment variable")

        if not cls.get_replicate_api_token():
            errors.append("REPLICATE_API_TOKEN not set. Configure via web UI at /api-config.html or set environment variable")

        return errors

    @classmethod
    def validate_script_length(cls, length: int) -> bool:
        """
        Validate script length is within allowed range

        Args:
            length: Requested script length in characters

        Returns:
            True if valid, False otherwise
        """
        return cls.MIN_SCRIPT_LENGTH <= length <= cls.MAX_SCRIPT_LENGTH

    @classmethod
    def get_config_info(cls):
        """Get configuration information for debugging"""
        return {
            'gemini_model': cls.GEMINI_MODEL,
            'replicate_model': cls.REPLICATE_MODEL,
            'images_per_video': cls.IMAGES_PER_VIDEO,
            'script_length_range': f"{cls.MIN_SCRIPT_LENGTH}-{cls.MAX_SCRIPT_LENGTH}",
            'default_script_length': cls.DEFAULT_SCRIPT_LENGTH,
            'data_dir': str(cls.DATA_DIR),
            'api_keys_set': {
                'gemini': bool(cls.get_gemini_api_key()),
                'replicate': bool(cls.get_replicate_api_token())
            }
        }


# Initialize directories on import
Config.ensure_directories()

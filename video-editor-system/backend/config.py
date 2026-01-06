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
        """Get Gemini API key from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('gemini_api_key') or os.getenv('GEMINI_API_KEY', '')

    @classmethod
    def get_replicate_api_token(cls):
        """Get Replicate API token from saved config or environment"""
        saved = cls._load_saved_config()
        return saved.get('replicate_api_token') or os.getenv('REPLICATE_API_TOKEN', '')

    # For backward compatibility, make them accessible as class attributes
    GEMINI_API_KEY = property(lambda self: self.get_gemini_api_key())
    REPLICATE_API_TOKEN = property(lambda self: self.get_replicate_api_token())

    @classmethod
    def save_api_config(cls, gemini_key=None, replicate_token=None):
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
        if replicate_token:
            config['replicate_api_token'] = replicate_token

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
            'config_file_exists': cls.API_CONFIG_FILE.exists()
        }

    # Gemini Settings
    GEMINI_MODEL = 'gemini-2.0-flash-exp'
    GEMINI_TEMPERATURE = 0.85
    GEMINI_MAX_TOKENS = 8192
    GEMINI_TOP_P = 0.92
    GEMINI_TOP_K = 35

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

    # Script generation settings
    TARGET_SCRIPT_LENGTH = 60000  # Target characters for script
    MIN_SCRIPT_LENGTH = 50000
    MAX_SCRIPT_LENGTH = 70000

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
    def get_config_info(cls):
        """Get configuration information for debugging"""
        return {
            'gemini_model': cls.GEMINI_MODEL,
            'replicate_model': cls.REPLICATE_MODEL,
            'images_per_video': cls.IMAGES_PER_VIDEO,
            'target_script_length': cls.TARGET_SCRIPT_LENGTH,
            'data_dir': str(cls.DATA_DIR),
            'api_keys_set': {
                'gemini': bool(cls.get_gemini_api_key()),
                'replicate': bool(cls.get_replicate_api_token())
            }
        }


# Initialize directories on import
Config.ensure_directories()

#!/usr/bin/env python3
"""
Configuration management for AI Video Generator
Handles API keys and system settings
"""

import os
from pathlib import Path

class Config:
    """Configuration manager for API keys and paths"""

    # API Keys (set via environment variables)
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN', '')

    # Gemini Settings
    GEMINI_MODEL = 'gemini-2.0-flash-exp'
    GEMINI_TEMPERATURE = 0.85
    GEMINI_MAX_TOKENS = 8192
    GEMINI_TOP_P = 0.92
    GEMINI_TOP_K = 35

    # Replicate Settings
    REPLICATE_MODEL = 'black-forest-labs/flux-schnell'
    REPLICATE_COST_PER_IMAGE = 0.003

    # Paths
    BASE_DIR = Path(__file__).parent.parent.resolve()
    BACKEND_DIR = BASE_DIR / 'backend'
    DATA_DIR = BASE_DIR / 'data'
    UPLOADS_DIR = BASE_DIR / 'uploads'
    OUTPUT_DIR = BASE_DIR / 'output'
    TEMP_DIR = BASE_DIR / 'temp'

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

        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY not set. Set environment variable or update config.py")

        if not cls.REPLICATE_API_TOKEN:
            errors.append("REPLICATE_API_TOKEN not set. Set environment variable or update config.py")

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
                'gemini': bool(cls.GEMINI_API_KEY),
                'replicate': bool(cls.REPLICATE_API_TOKEN)
            }
        }


# Initialize directories on import
Config.ensure_directories()

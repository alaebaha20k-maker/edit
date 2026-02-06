#!/usr/bin/env python3
"""
Settings Manager for AI Video Generator
Handles API keys, generation formulas, and voice configurations
"""

import json
import re
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
    DEFAULT_TITLE_FORMULA = """═══════════════════════════════════════════════════════
TITLE GENERATION FORMULA
═══════════════════════════════════════════════════════

TITLE STRUCTURE:
[Power Hook] + [Core Topic] + [Value Promise]

COMPONENTS TO USE:
• Power Hooks: The Hidden, What, How, Why, The Secret, The Truth About, Inside, Behind
• Value Promises: That Changed Everything, Nobody Tells You, You Need to Know, Elite Traders Use, Wall Street Hides, Actually Works

HIGH-QUALITY EXAMPLES:
1. The Hidden Pattern That Made Jesse Livermore $100M
2. What Elite Traders Know About Market Psychology
3. Inside the Strategy Wall Street Doesn't Want You to See
4. The Truth About Trading Psychology Nobody Tells You
5. How One Mistake Cost Livermore His Fortune

QUALITY REQUIREMENTS:
✓ Follow the structure/pattern exactly
✓ Use ONLY components from the lists provided
✓ 45-70 characters preferred (max 100)
✓ NO clickbait words: amazing, shocking, incredible
✓ NO emojis in the title
✓ Trigger curiosity and promise value
✓ Use power words: Hidden, Forbidden, Ancient, Elite, Silent, Untold, Final, Last
✓ Be specific: use numbers, names, timeframes when possible

CONTEXT (will be filled by system):
Topic: {topic}
Niche: {niche}
Language: {language}

INSTRUCTIONS FOR AI:
Generate titles that STRICTLY follow the structure above using ONLY the provided components.
Each title must be distinctive, high-quality, and optimized for CTR."""

    DEFAULT_SCRIPT_FORMULA = """═══════════════════════════════════════════════════════
SCRIPT GENERATION FORMULA
═══════════════════════════════════════════════════════

NARRATIVE STRUCTURE:
1. HOOK (First 10-15 seconds)
   - Open with a provocative question, shocking fact, or tension
   - Create immediate curiosity
   - Avoid explaining or summarizing
   - Make the listener need to know more

2. SETUP & PROMISE (Next 1-2 minutes)
   - Establish the problem, mystery, or opportunity
   - Position the viewer as the hero who needs this knowledge
   - Make a clear promise: "By the end, you'll understand..."
   - Use specific examples, not generalities

3. JOURNEY (Middle 60% of script)
   - Weave facts with stories and examples
   - Build complexity gradually
   - Include mini-revelations every 90 seconds
   - Use metaphors and analogies for clarity
   - Vary sentence length: short for impact, longer for depth
   - Use pattern interrupts: "But here's where it gets interesting..."

4. TRANSFORMATION (Final 20%)
   - Synthesize everything into clear insights
   - Provide actionable takeaways
   - Create a memorable closing statement
   - Echo the opening hook with new meaning

VOICE & TONE:
- Natural, conversational, intelligent
- Authoritative but not arrogant
- Passionate but not hysterical
- Use direct address: "You've probably experienced this..."
- Rhetorical questions to re-engage

RHYTHM TECHNIQUES:
- Short sentences for emphasis. Like this.
- Longer flowing sentences for complex ideas that need context.
- Strategic repetition: "Not tomorrow. Not next week. Today."
- Power verbs: transformed, shattered, unveiled, engineered

WORD CHOICE:
- Concrete over abstract: "47% increase" not "significant growth"
- Sensory language: "razor-sharp," "crystalline"
- Avoid filler: very, really, quite, basically, actually
- Create tension and release

CRITICAL OUTPUT RULES:
✓ Plain text ONLY - no markdown, bullets, formatting, emojis
✓ No timestamps, section headers, or stage directions
✓ No visual cues like "VISUALS:" or "VIDEO:"
✓ No meta-commentary or explanations
✓ Pure spoken narration ready for TTS
✓ Natural speech patterns with strategic pauses

TARGET LENGTH: {target_length} characters (~{word_count} words)
LANGUAGE: {language}
NICHE: {niche}

Write a script that sounds deeply human, emotionally engaging, and perfectly voice-ready."""

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

    # Inworld AI voice configurations (Official Inworld TTS-1.5 Voices)
    INWORLD_VOICES = {
        # Female voices
        'olivia': {
            'name': 'Olivia',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Elegant, smooth voice - perfect for professional content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/olivia_preview.mp3'
        },
        'sarah': {
            'name': 'Sarah',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Warm, engaging voice - great for storytelling',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/sarah_preview.mp3'
        },
        'ashley': {
            'name': 'Ashley',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Energetic, bright voice - ideal for entertainment',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/ashley_preview.mp3'
        },
        'elizabeth': {
            'name': 'Elizabeth',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Professional, clear voice - excellent for educational content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/elizabeth_preview.mp3'
        },
        'wendy': {
            'name': 'Wendy',
            'language': 'en-US',
            'gender': 'Female',
            'description': 'Soft, gentle voice - perfect for calm narration',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/wendy_preview.mp3'
        },
        # Male voices
        'dennis': {
            'name': 'Dennis',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Deep, authoritative voice - great for documentaries',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/dennis_preview.mp3'
        },
        'mark': {
            'name': 'Mark',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Professional, clear voice - perfect for business content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/mark_preview.mp3'
        },
        'theodore': {
            'name': 'Theodore',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Warm, friendly voice - ideal for tutorials',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/theodore_preview.mp3'
        },
        'edward': {
            'name': 'Edward',
            'language': 'en-GB',
            'gender': 'Male',
            'description': 'British, refined voice - excellent for sophisticated content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/edward_preview.mp3'
        },
        'craig': {
            'name': 'Craig',
            'language': 'en-US',
            'gender': 'Male',
            'description': 'Strong, confident voice - great for motivational content',
            'preview_url': 'https://storage.googleapis.com/inworld-ai-samples/craig_preview.mp3'
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
                'default_voice': 'olivia',
                'speaking_rate': 1.0
            }
        }

    @classmethod
    def save_api_keys(cls, gemini: str = None, director_gemini: str = None,
                     replicate: str = None, inworld: str = None, pexels: str = None) -> Dict:
        """
        Save API keys to settings file

        Args:
            gemini: Gemini API key (for script writing)
            director_gemini: Director Gemini API key (for Auto Images AI)
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
        if director_gemini is not None:
            settings['api_keys']['director_gemini'] = director_gemini
        if replicate is not None:
            settings['api_keys']['replicate'] = replicate
        if inworld is not None:
            settings['api_keys']['inworld'] = inworld
        if pexels is not None:
            settings['api_keys']['pexels'] = pexels

        # Save to file
        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)

        # Also update Config (used by other modules)
        from config import Config
        Config.save_api_config(
            gemini_key=gemini if gemini else None,
            director_gemini_key=director_gemini if director_gemini else None,
            replicate_token=replicate if replicate else None,
            inworld_key=inworld if inworld else None
        )

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
    def _transform_title_formula(cls, raw_formula: str) -> str:
        """
        AUTO-TRANSFORM any formula into a proven high-quality structure

        This ensures Gemini ALWAYS receives a well-structured prompt
        that produces high-quality titles, no matter what the user enters.

        Args:
            raw_formula: User's raw formula input (any format)

        Returns:
            Transformed formula in proven structure
        """
        # Extract key information from raw formula
        lines = raw_formula.strip().split('\n')

        # Try to identify structure/pattern
        structure_pattern = None
        components = {}
        examples = []

        for line in lines:
            line_lower = line.lower().strip()

            # Look for structure/pattern lines
            if any(keyword in line_lower for keyword in ['structure:', 'pattern:', 'format:', 'basic structure']):
                # Extract the pattern (text after the keyword)
                structure_pattern = line.split(':', 1)[-1].strip()
                # Clean up markdown
                structure_pattern = re.sub(r'[`*#]', '', structure_pattern)

            # Look for component lists
            elif ':' in line and not line_lower.startswith(('http', 'example')):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().strip('*#-').lower()
                    value = parts[1].strip()
                    # Store component lists
                    if key and value:
                        components[key] = value

            # Look for examples
            elif any(keyword in line_lower for keyword in ['example:', '✅', '❌ bad', '✓ good']):
                cleaned = re.sub(r'^[✅❌✓✗\-\*#•]+\s*(good|bad|example)?:?\s*', '', line, flags=re.IGNORECASE).strip()
                cleaned = re.sub(r'[`*"]', '', cleaned)
                if cleaned and len(cleaned) > 10:
                    examples.append(cleaned)

        # Build the PROVEN STRUCTURE that always works
        transformed = f"""═══════════════════════════════════════════════════════
TITLE GENERATION FORMULA
═══════════════════════════════════════════════════════

"""

        # Add structure pattern if found
        if structure_pattern:
            transformed += f"""TITLE STRUCTURE:
{structure_pattern}

"""

        # Add components if found
        if components:
            transformed += """COMPONENTS TO USE:
"""
            for key, value in components.items():
                # Format key nicely
                key_formatted = key.replace('_', ' ').title()
                transformed += f"• {key_formatted}: {value}\n"
            transformed += "\n"

        # Add examples if found
        if examples:
            transformed += """HIGH-QUALITY EXAMPLES:
"""
            for i, example in enumerate(examples[:5], 1):  # Max 5 examples
                transformed += f"{i}. {example}\n"
            transformed += "\n"

        # Add quality requirements (ALWAYS)
        transformed += """QUALITY REQUIREMENTS:
✓ Follow the structure/pattern exactly
✓ Use ONLY components from the lists provided
✓ 45-70 characters preferred (max 100)
✓ NO clickbait words: amazing, shocking, incredible
✓ NO emojis in the title
✓ Trigger curiosity and promise value
✓ Use power words: Hidden, Forbidden, Ancient, Elite, Silent, Untold, Final, Last
✓ Be specific: use numbers, names, timeframes when possible

"""

        # Add placeholders for backend integration
        transformed += """CONTEXT (will be filled by system):
Topic: {topic}
Niche: {niche}
Language: {language}

INSTRUCTIONS FOR AI:
Generate titles that STRICTLY follow the structure above using ONLY the provided components.
Each title must be distinctive, high-quality, and optimized for CTR.
"""

        return transformed

    @classmethod
    def save_formulas(cls, title_formula: str = None, script_formula: str = None,
                     image_formula: str = None) -> bool:
        """
        Save generation formulas to text files

        AUTO-TRANSFORMS title formulas into proven high-quality structure
        before saving, ensuring Gemini always produces excellent results.

        Args:
            title_formula: Template for title generation (any format - will be auto-transformed)
            script_formula: Template for script generation
            image_formula: Template for image prompt generation

        Returns:
            True if successful
        """
        cls.ensure_directories()

        try:
            if title_formula is not None:
                # AUTO-TRANSFORM title formula into proven structure
                transformed = cls._transform_title_formula(title_formula)
                with open(cls.TITLE_FORMULA_FILE, 'w') as f:
                    f.write(transformed)
                print("✅ Title formula auto-transformed into high-quality structure")

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
            default_voice: Voice ID (e.g., 'olivia', 'dennis', 'sarah')
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
            'default_voice': 'olivia',
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
            'director_gemini': {
                'configured': bool(api_keys.get('director_gemini')),
                'required': False  # Optional - falls back to regular gemini key
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
                for key in ['gemini', 'director_gemini', 'replicate', 'inworld', 'pexels']
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

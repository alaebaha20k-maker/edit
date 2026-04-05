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
    # DATA_DIR lives OUTSIDE the git repo so it survives git pull / fresh clone
    DATA_DIR = Path.home() / '.video-editor-data'
    SETTINGS_FILE = DATA_DIR / 'settings.json'

    # Formula files
    FORMULAS_DIR = DATA_DIR / 'formulas'
    TITLE_FORMULA_FILE = FORMULAS_DIR / 'title_formula.txt'
    SCRIPT_FORMULA_FILE = FORMULAS_DIR / 'script_formula.txt'
    IMAGE_FORMULA_FILE = FORMULAS_DIR / 'image_formula.txt'
    AUTO_IMAGES_FORMULA_FILE = FORMULAS_DIR / 'auto_images_formula.txt'
    SEO_FORMULA_FILE = FORMULAS_DIR / 'seo_formula.txt'

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

    DEFAULT_AUTO_IMAGES_FORMULA = """═══════════════════════════════════════════════════════════
AUTO IMAGES FORMULA — CREATIVE INSTRUCTIONS
═══════════════════════════════════════════════════════════
Available placeholders: {n_images} {style_name} {lighting} {composition} {color_palette}
These are automatically replaced when generating prompts.
═══════════════════════════════════════════════════════════

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {n_images} scenes (NO MORE, NO LESS)
2. Scenes MUST be CHRONOLOGICAL (beginning → end of script)
3. Each scene covers a DISTINCT part of the story
4. NO REPETITION — each scene is completely unique
5. Each prompt MUST be 300+ CHARACTERS with EXTREME DETAIL
6. Focus on VISUAL STORYTELLING — images tell the story without text
7. ALL image prompts MUST be written in ENGLISH (regardless of script language)

═══════════════════════════════════════════════════════════
CREATIVE SCENE PRINCIPLES
═══════════════════════════════════════════════════════════

1. SHOW, DON'T TELL
   - Instead of "person looking sad" → "woman in her 30s with red-rimmed eyes and tear-stained cheeks, shoulders slumped, staring blankly at an empty coffee cup on a rain-streaked window sill"
   - Instead of "office workspace" → "cluttered mahogany desk with scattered papers, overflowing inbox, cold half-finished coffee, illuminated by harsh fluorescent overhead lights"

2. EMOTIONAL DEPTH THROUGH DETAILS
   - Small details reveal emotion: trembling hands, clenched jaw, forced smile, distant gaze
   - Environment reflects mood: warm golden hour for hope, harsh shadows for tension, soft diffused light for peace
   - Body language tells stories: confident stance vs defensive posture, open arms vs crossed arms

3. CINEMATIC COMPOSITION TECHNIQUES
   - Rule of thirds: Position key elements at intersection points for dynamic composition
   - Leading lines: Use roads, railings, shadows to guide viewer's eye to subject
   - Depth layers: Foreground, mid-ground, background create immersive 3D feeling
   - Frame within frame: Doorways, windows, arches focus attention on subject

4. LIGHTING AS EMOTION
   - Golden hour: Warmth, hope, nostalgia, romance
   - Blue hour: Mystery, contemplation, transition, melancholy
   - Harsh noon sun: Clarity, exposure, harsh reality, intensity
   - Dramatic side lighting: Tension, conflict, duality, revelation
   - Backlight/rim light: Heroic, ethereal, mysterious, dramatic

5. COLOR PSYCHOLOGY FOR MOOD
   - Warm tones (red, orange, yellow): Energy, passion, urgency, excitement
   - Cool tones (blue, cyan, teal): Calm, technology, sadness, distance
   - Desaturated/muted: Serious, documentary, realistic, somber
   - Complementary colors: Visual tension and energy (blue/orange, purple/yellow)

6. MATCH SCENES TO SCRIPT CONTENT TYPE
   - Educational/Tutorial content → Clean, bright, organized visuals with clear focus
   - Dramatic/Story content → Cinematic lighting, emotional expressions, narrative moments
   - Tech/Business content → Modern, sleek, professional environments with cool tones
   - Nature/Travel content → Epic landscapes, golden hour lighting, sense of scale

7. CAMERA ANGLE PSYCHOLOGY
   - Eye level: Neutral, relatable, documentary style
   - Low angle (looking up): Power, dominance, heroic, impressive
   - High angle (looking down): Vulnerability, weakness, overview, context
   - Dutch angle (tilted): Unease, tension, disorientation, chaos
   - Bird's eye view: Scale, pattern, planning, overview

8. DEPTH OF FIELD STORYTELLING
   - Shallow (blurred background): Focus on subject, intimacy, isolation
   - Deep (everything sharp): Context importance, environment as character

9. VISUAL METAPHORS AND SYMBOLISM
   - Weather matches emotion: Storm = turmoil, sunshine = happiness, fog = confusion
   - Objects tell stories: Wilted flower = lost hope, rising smoke = fleeting time
   - Positioning shows relationships: Close = connection, separated = distance

10. PROFESSIONAL POLISH
    - Specific materials and textures: "brushed aluminum", "weathered leather", "glossy marble"
    - Exact time of day: "early morning mist at 6am", "golden hour at 7:30pm"
    - Precise clothing details: "navy blue suit with white pocket square"
    - Technical camera terms: "85mm lens at f/1.4", "35mm wide angle", "macro close-up"

═══════════════════════════════════════════════════════════
PROMPT QUALITY RULES (MANDATORY)
═══════════════════════════════════════════════════════════

Each image_prompt MUST include ALL of these elements:
1. SUBJECT: Who/what — age, appearance, clothing, expression, body language
2. SETTING: Specific environment — location, time of day, background elements, atmosphere
3. ACTION: Exact moment — pose, movement, interaction, emotion
4. CAMERA: Shot type and angle (wide shot, close-up, dutch angle, over-shoulder, bird's eye, etc.)
5. LIGHTING: Detailed lighting matching style ({lighting})
6. COMPOSITION: Framing matching style ({composition})
7. STYLE TOKENS: Include "{style_name}" style
8. COLOR GUIDANCE: Use colors from palette ({color_palette}) with color psychology
9. QUALITY: "professional photography, high resolution, sharp focus, detailed"
10. TEXTURE & DETAILS: Materials, surfaces, depth of field, reflections

EXAMPLE EXCELLENT PROMPT:
"A determined young trader in his late 20s with short dark hair and focused expression, wearing a pressed white shirt with rolled sleeves, sitting at a modern glass desk in a corner office with floor-to-ceiling windows overlooking a golden-hour city skyline, leaning forward studying three glowing monitors with candlestick charts, medium close-up from 45-degree angle, warm golden sunlight creating dramatic rim lighting mixed with cool blue monitor glow, {style_name} style, 85mm lens f/2.8, rich warm golds and cool blues, professional photography, 8k quality, cinematic"

═══════════════════════════════════════════════════════════
SCENE DISTRIBUTION STRATEGY
═══════════════════════════════════════════════════════════
- If N = 1: ONLY the very first opening scene
- If N = 2: Opening scene + final conclusion scene
- If N = 3-5: Major story beats only (intro, climax, conclusion)
- If N = 6-10: Key moments from each story section
- If N = 11-20: Detailed coverage with transitions
- If N = 21-50: Granular scene-by-scene progression
- If N = 51+: Nearly every sentence gets a visual"""

    DEFAULT_SEO_FORMULA = """INSTRUCTIONS:
Write a high-quality YouTube description and tags for a video in the detected language.

DESCRIPTION STRUCTURE:
1. OPENING (2-3 sentences): Hook directly connected to the video title. Identify the viewer's problem.
2. BODY (3-5 bullet points with •): Key things the viewer will learn or discover from the video.
3. CTA SECTION: Natural mention of the product/link with a short compelling sentence about what's behind it.
   Format: 👉 {link}
4. CHAPTERS SECTION (⏱ CHAPITRES / ⏱ CHAPTERS):
   Format each chapter as: 00:00 — Chapter title
   Create 5-10 logical chapters from the script content.
5. CLOSING LINE: One line inviting to subscribe / follow.

TAGS RULES:
- Comma-separated, total MUST be under 400 characters
- Start with the most specific tags (exact title keywords), then broader related terms
- Mix short tags (2-3 words) and long-tail tags (4-5 words)
- All tags in the same language as the video

LANGUAGE: Auto-detect from title and script. Write EVERYTHING in that language."""

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
        },
        # French voices (fr-FR)
        'mathieu': {
            'name': 'Mathieu',
            'language': 'fr-FR',
            'gender': 'Male',
            'description': 'Voix masculine naturelle - idéale pour les contenus professionnels',
            'preview_url': ''
        },
        'helene': {
            'name': 'Hélène',
            'language': 'fr-FR',
            'gender': 'Female',
            'description': 'Voix féminine douce et élégante - parfaite pour la narration',
            'preview_url': ''
        },
        'etienne': {
            'name': 'Étienne',
            'language': 'fr-FR',
            'gender': 'Male',
            'description': 'Voix masculine chaleureuse - excellente pour le storytelling',
            'preview_url': ''
        },
        'alain': {
            'name': 'Alain',
            'language': 'fr-FR',
            'gender': 'Male',
            'description': 'Voix masculine profonde et autoritaire - idéale pour les documentaires',
            'preview_url': ''
        },
        # German voices (de-DE)
        'johanna': {
            'name': 'Johanna',
            'language': 'de-DE',
            'gender': 'Female',
            'description': 'Ruhige ältere deutsche Stimme, tief und rauchig',
            'preview_url': ''
        },
        'josef': {
            'name': 'Josef',
            'language': 'de-DE',
            'gender': 'Male',
            'description': 'Männliche deutsche Stimme, klar und professionell',
            'preview_url': ''
        },
        # Spanish voices (es-ES)
        'diego': {
            'name': 'Diego',
            'language': 'es-ES',
            'gender': 'Male',
            'description': 'Voz masculina suave y calmada, perfecta para narración',
            'preview_url': ''
        },
        'lupita': {
            'name': 'Lupita',
            'language': 'es-ES',
            'gender': 'Female',
            'description': 'Voz femenina joven, vibrante y enérgica',
            'preview_url': ''
        },
        'miguel': {
            'name': 'Miguel',
            'language': 'es-ES',
            'gender': 'Male',
            'description': 'Voz masculina adulta calmada, perfecta para storytelling',
            'preview_url': ''
        },
        'rafael': {
            'name': 'Rafael',
            'language': 'es-ES',
            'gender': 'Male',
            'description': 'Voz masculina profunda y serena, ideal para narración',
            'preview_url': ''
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
                'director_gemini': '',
                'replicate': '',
                'inworld': '',
                'inworld_secret': '',
                'pexels': '',
                'pixabay': ''
            },
            'voice_settings': {
                'default_voice': 'olivia',
                'speaking_rate': 1.0
            },
            'video_settings': {
                'enable_timed_zoom': False,
                'zoom_direction': 'in',  # 'in' or 'out'
                'zoom_duration': 1.0,    # seconds
                'zoom_amount': 1.05      # zoom factor (1.05 = 5% zoom)
            }
        }

    @classmethod
    def save_api_keys(cls, gemini: str = None, director_gemini: str = None,
                     gemini_image: str = None,
                     replicate: str = None, inworld: str = None, inworld_secret: str = None,
                     pexels: str = None, pixabay: str = None, unsplash: str = None,
                     brave_search: str = None, serper: str = None,
                     google_search: str = None, videvo: str = None, coverr: str = None,
                     gemini_translate_1: str = None, gemini_translate_2: str = None,
                     gemini_prompts: str = None, gemini_seo: str = None) -> Dict:
        """
        Save API keys to settings file

        Args:
            gemini: Gemini API key (for script writing)
            director_gemini: Director Gemini API key (for Auto Images AI)
            gemini_image: Gemini Image API key (for Gemini 2.5 Flash image generation)
            replicate: Replicate API token
            inworld: Inworld AI API key
            inworld_secret: Inworld AI API secret
            pexels: Pexels API key
            pixabay: Pixabay API key

        Returns:
            Updated settings dictionary
        """
        cls.ensure_directories()
        settings = cls.load_settings()

        # Ensure all keys exist in settings
        if 'api_keys' not in settings:
            settings['api_keys'] = {}

        # Update only provided keys (skip empty strings - only save actual keys)
        if gemini is not None and gemini != '':
            settings['api_keys']['gemini'] = gemini
        if director_gemini is not None and director_gemini != '':
            settings['api_keys']['director_gemini'] = director_gemini
        if gemini_image is not None and gemini_image != '':
            settings['api_keys']['gemini_image'] = gemini_image
        if replicate is not None and replicate != '':
            settings['api_keys']['replicate'] = replicate
        if inworld is not None and inworld != '':
            settings['api_keys']['inworld'] = inworld
        if inworld_secret is not None and inworld_secret != '':
            settings['api_keys']['inworld_secret'] = inworld_secret
        if pexels is not None and pexels != '':
            settings['api_keys']['pexels'] = pexels
        if pixabay is not None and pixabay != '':
            settings['api_keys']['pixabay'] = pixabay
        if unsplash is not None and unsplash != '':
            settings['api_keys']['unsplash'] = unsplash
        if brave_search is not None and brave_search != '':
            settings['api_keys']['brave_search'] = brave_search
        if serper is not None and serper != '':
            settings['api_keys']['serper'] = serper
        if google_search is not None and google_search != '':
            settings['api_keys']['google_search'] = google_search
        if videvo is not None and videvo != '':
            settings['api_keys']['videvo'] = videvo
        if coverr is not None and coverr != '':
            settings['api_keys']['coverr'] = coverr
        if gemini_translate_1 is not None and gemini_translate_1 != '':
            settings['api_keys']['gemini_translate_1'] = gemini_translate_1
        if gemini_translate_2 is not None and gemini_translate_2 != '':
            settings['api_keys']['gemini_translate_2'] = gemini_translate_2
        if gemini_prompts is not None and gemini_prompts != '':
            settings['api_keys']['gemini_prompts'] = gemini_prompts
        if gemini_seo is not None and gemini_seo != '':
            settings['api_keys']['gemini_seo'] = gemini_seo

        # Save to file
        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)

        # Also update Config (used by other modules like voice_generator)
        from config import Config
        Config.save_api_config(
            gemini_key=gemini if gemini else None,
            director_gemini_key=director_gemini if director_gemini else None,
            gemini_image_key=gemini_image if gemini_image else None,
            replicate_token=replicate if replicate else None,
            inworld_key=inworld if inworld else None,
            inworld_secret=inworld_secret if inworld_secret else None,
            gemini_translate_1=gemini_translate_1 if gemini_translate_1 else None,
            gemini_translate_2=gemini_translate_2 if gemini_translate_2 else None,
            gemini_prompts_key=gemini_prompts if gemini_prompts else None,
            gemini_seo_key=gemini_seo if gemini_seo else None
        )

        return settings

    @classmethod
    def get_api_key(cls, key_name: str) -> str:
        """
        Get a specific API key

        Args:
            key_name: One of 'gemini', 'replicate', 'inworld', 'pexels', 'pixabay'

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
                     image_formula: str = None, auto_images_formula: str = None,
                     seo_formula: str = None) -> bool:
        """Save generation formulas to text files."""
        cls.ensure_directories()

        try:
            if title_formula is not None:
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

            if auto_images_formula is not None:
                with open(cls.AUTO_IMAGES_FORMULA_FILE, 'w') as f:
                    f.write(auto_images_formula)

            if seo_formula is not None:
                with open(cls.SEO_FORMULA_FILE, 'w') as f:
                    f.write(seo_formula)

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
            'title':       (cls.TITLE_FORMULA_FILE,       cls.DEFAULT_TITLE_FORMULA),
            'script':      (cls.SCRIPT_FORMULA_FILE,      cls.DEFAULT_SCRIPT_FORMULA),
            'image':       (cls.IMAGE_FORMULA_FILE,       cls.DEFAULT_IMAGE_FORMULA),
            'auto_images': (cls.AUTO_IMAGES_FORMULA_FILE, cls.DEFAULT_AUTO_IMAGES_FORMULA),
            'seo':         (cls.SEO_FORMULA_FILE,         cls.DEFAULT_SEO_FORMULA),
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
    def save_video_settings(cls, enable_timed_zoom: bool = None,
                           zoom_direction: str = None,
                           zoom_duration: float = None,
                           zoom_amount: float = None) -> Dict:
        """
        Save video zoom settings

        Args:
            enable_timed_zoom: Enable/disable timed zoom effect for images
            zoom_direction: 'in' (zoom in) or 'out' (zoom out)
            zoom_duration: Duration of zoom effect in seconds (default 1.0)
            zoom_amount: Zoom factor (default 1.05 for 5% zoom)

        Returns:
            Updated settings dictionary
        """
        cls.ensure_directories()
        settings = cls.load_settings()

        if 'video_settings' not in settings:
            settings['video_settings'] = cls._get_default_settings()['video_settings']

        if enable_timed_zoom is not None:
            settings['video_settings']['enable_timed_zoom'] = bool(enable_timed_zoom)

        if zoom_direction is not None:
            if zoom_direction not in ['in', 'out']:
                raise ValueError("zoom_direction must be 'in' or 'out'")
            settings['video_settings']['zoom_direction'] = zoom_direction

        if zoom_duration is not None:
            if not 0.1 <= zoom_duration <= 5.0:
                raise ValueError("zoom_duration must be between 0.1 and 5.0 seconds")
            settings['video_settings']['zoom_duration'] = float(zoom_duration)

        if zoom_amount is not None:
            if not 1.01 <= zoom_amount <= 2.0:
                raise ValueError("zoom_amount must be between 1.01 and 2.0")
            settings['video_settings']['zoom_amount'] = float(zoom_amount)

        with open(cls.SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)

        return settings

    @classmethod
    def get_video_settings(cls) -> Dict:
        """Get current video zoom settings"""
        settings = cls.load_settings()
        return settings.get('video_settings', {
            'enable_timed_zoom': False,
            'zoom_direction': 'in',
            'zoom_duration': 1.0,
            'zoom_amount': 1.05
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
                'configured': bool(api_keys.get('inworld') and api_keys.get('inworld_secret')),
                'required': False  # Optional for now
            },
            'pexels': {
                'configured': bool(api_keys.get('pexels')),
                'required': False  # Optional for now
            },
            'pixabay': {
                'configured': bool(api_keys.get('pixabay')),
                'required': False
            },
            'gemini_translate_1': {
                'configured': bool(api_keys.get('gemini_translate_1')),
                'required': False
            },
            'gemini_translate_2': {
                'configured': bool(api_keys.get('gemini_translate_2')),
                'required': False
            }
        }

    @classmethod
    def get_settings_summary(cls) -> Dict:
        """Get a summary of all settings for display"""
        settings = cls.load_settings()
        api_validation = cls.validate_api_keys()

        # Get all API keys from settings
        api_keys_dict = settings.get('api_keys', {})

        return {
            'api_keys': {
                key: {
                    'configured': api_validation[key]['configured'],
                    'value': '***' if api_keys_dict.get(key) else ''
                }
                for key in ['gemini', 'director_gemini', 'gemini_image', 'replicate', 'inworld',
                            'pexels', 'pixabay', 'gemini_translate_1', 'gemini_translate_2']
            },
            'formulas': {
                'title': len(cls.load_formula('title')),
                'script': len(cls.load_formula('script')),
                'image': len(cls.load_formula('image'))
            },
            'voice_settings': cls.get_voice_settings(),
            'video_settings': cls.get_video_settings(),
            'available_voices': len(cls.INWORLD_VOICES)
        }


# Initialize directories on import
SettingsManager.ensure_directories()

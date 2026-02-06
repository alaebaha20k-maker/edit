"""
Gemini Director Client - Separate Gemini instance for image planning
CRITICAL: Uses SEPARATE credentials from script writer Gemini
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional
import google.generativeai as genai
from pydantic import ValidationError

from .schema import AutoImagesPlan


class DirectorClient:
    """Gemini Director for planning auto-generated images"""

    DIRECTOR_VERSION = "v1.0"
    CACHE_DIR = Path("cache/director_plans")

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        """
        Initialize Director Gemini client

        Args:
            api_key: SEPARATE Gemini API key for Director (not script writer!)
            model_name: Gemini model to use (default: gemini-2.5-flash, same as script generator)
        """
        if not api_key:
            raise ValueError("Director Gemini API key is required")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 0.7,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 8192,
            }
        )

        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, script_text: str, style: Dict, n_images: int) -> str:
        """Generate cache key for plan"""
        data = f"{script_text}|{style.get('id', 'default')}|{n_images}|{self.DIRECTOR_VERSION}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _load_cached_plan(self, cache_key: str) -> Optional[AutoImagesPlan]:
        """Load cached plan if exists"""
        cache_file = self.CACHE_DIR / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                return AutoImagesPlan(**data)
            except Exception as e:
                print(f"Failed to load cache: {e}")
                return None
        return None

    def _save_cached_plan(self, cache_key: str, plan: AutoImagesPlan):
        """Save plan to cache"""
        cache_file = self.CACHE_DIR / f"{cache_key}.json"
        with open(cache_file, 'w') as f:
            json.dump(plan.dict(), f, indent=2)

    def _build_director_prompt(self, script_text: str, style: Dict, n_images: int) -> str:
        """Build the Director prompt with all requirements"""

        style_name = style.get('name', 'Cinematic')
        style_description = style.get('description', 'High-quality cinematic style')

        # Extract style details from the style dict
        visual_rules = style.get('visual_rules', [])
        negative_rules = style.get('negative_rules', [])
        composition_style = style.get('composition', 'Professional composition')
        lighting_style = style.get('lighting', 'Dramatic lighting')
        color_palette = style.get('color_palette', ['Rich colors'])

        # Build visual rules section
        visual_rules_text = '\n'.join([f"   - {rule}" for rule in visual_rules])
        negative_rules_text = '\n'.join([f"   - {rule}" for rule in negative_rules])
        color_palette_text = ', '.join(color_palette)

        prompt = f"""You are an AI Director planning visual scenes for a video. You MUST create HIGHLY DETAILED, PROFESSIONAL QUALITY prompts that EXACTLY match the chosen style.

TASK: Create {n_images} DETAILED image generation prompts from this script.

SCRIPT:
{script_text}

═══════════════════════════════════════════════════════════
STYLE BIBLE: {style_name}
═══════════════════════════════════════════════════════════
Description: {style_description}

VISUAL RULES (MUST FOLLOW EXACTLY):
{visual_rules_text}

NEGATIVE RULES (MUST AVOID):
{negative_rules_text}

Composition: {composition_style}
Lighting: {lighting_style}
Color Palette: {color_palette_text}
═══════════════════════════════════════════════════════════

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {n_images} scenes (NO MORE, NO LESS)
2. Scenes MUST be CHRONOLOGICAL (beginning → end of script)
3. Each scene covers a DISTINCT part of the story
4. NO REPETITION - each scene is completely unique
5. Each prompt MUST be 80-150 WORDS with extreme detail

PROMPT QUALITY RULES (MANDATORY - NO EXCEPTIONS):

Each "image_prompt" MUST include ALL of these elements:

1. SUBJECT: Detailed description of who/what (age, appearance, clothing, expression)
2. SETTING: Specific environment details (location type, background elements, atmosphere)
3. ACTION: Exact moment being captured (pose, movement, interaction)
4. CAMERA: Specific shot type and angle (wide shot, close-up, dutch angle, over-shoulder, etc.)
5. LIGHTING: Detailed lighting description matching style ({lighting_style})
6. COMPOSITION: Framing that matches style ({composition_style})
7. STYLE TOKENS: Include "{style_name}" style
8. COLOR GUIDANCE: Use colors from palette ({color_palette_text})
9. QUALITY: Add "professional photography, high resolution, sharp focus, detailed"
10. TEXTURE & DETAILS: Materials, surfaces, depth of field

EXAMPLE OF GOOD PROMPT (This is the level of detail required):
"A determined young trader in his late 20s with short dark hair and focused expression, wearing a crisp white shirt, sitting at a modern glass desk in a sleek minimalist office with floor-to-ceiling windows overlooking a city skyline at golden hour, leaning forward studying multiple glowing monitors displaying colorful trading charts and data, medium close-up shot from a slight side angle capturing both his concentrated face and the illuminated screens, warm golden sunlight streaming through windows creating dramatic rim lighting on his profile while cool blue monitor glow illuminates his face, {style_name} style, shallow depth of field with sharp focus on subject and soft bokeh background, rich warm golds and cool blues color palette, professional photography, high resolution, 8k quality, sharp details"

EXAMPLE OF BAD PROMPT (DO NOT DO THIS):
"Trader at desk looking at computer, {style_name} style"

Each "negative_prompt" MUST include:
- All negative rules from style bible
- Generic quality issues: "low quality, blurry, distorted, pixelated, jpeg artifacts"
- Technical issues: "overexposed, underexposed, bad lighting, poor composition"
- Unwanted elements: "text, watermarks, signatures, logos, banners"
- Style violations: Elements that contradict the chosen style

SCENE DISTRIBUTION STRATEGY:
- If N = 3-5: Major story beats only (intro, climax, conclusion)
- If N = 6-10: Key moments from each story section
- If N = 11-20: Detailed coverage with transitions
- If N = 21-50: Granular scene-by-scene progression
- If N = 51-100: Nearly every sentence gets a visual

OUTPUT FORMAT (STRICT JSON - NO MARKDOWN):
{{
  "mode": "auto_images",
  "style_id": "{style.get('id', 'cinematic')}",
  "n_images": {n_images},
  "global_style_bible": {{
    "style_name": "{style_name}",
    "visual_rules": {visual_rules},
    "negative_rules": {negative_rules},
    "composition": "{composition_style}",
    "lighting": "{lighting_style}",
    "color_palette": {color_palette}
  }},
  "scenes": [
    {{
      "scene_id": 1,
      "scene_summary": "What happens in this part of the story",
      "narration_focus": "What the script talks about here",
      "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
      "image_prompt": "DETAILED 80-150 WORD PROMPT including subject, setting, action, camera angle, lighting matching {lighting_style}, composition matching {composition_style}, {style_name} style, color palette using {color_palette_text}, professional quality, high resolution, sharp focus, detailed textures",
      "negative_prompt": "low quality, blurry, distorted, pixelated, jpeg artifacts, overexposed, underexposed, bad lighting, poor composition, text, watermarks, signatures, {', '.join(negative_rules)}"
    }},
    ... (exactly {n_images} scenes total)
  ]
}}

MANDATORY SELF-CHECK BEFORE OUTPUTTING:
✓ Number of scenes = {n_images} EXACTLY?
✓ Scenes are chronological from start to end of script?
✓ Each scene is completely unique (no repetition)?
✓ Each image_prompt is 80-150 WORDS with extreme detail?
✓ Each image_prompt includes: subject, setting, action, camera, lighting, composition, style tokens, colors, quality?
✓ All visual rules from style bible applied consistently?
✓ All negative rules from style bible included in negative_prompts?
✓ Lighting matches: {lighting_style}?
✓ Composition matches: {composition_style}?
✓ Color palette uses: {color_palette_text}?

OUTPUT ONLY VALID JSON. NO MARKDOWN. NO EXPLANATION.
"""
        return prompt

    def _parse_json_response(self, response_text: str) -> Dict:
        """Parse JSON from Gemini response, handling markdown fences"""
        # Remove markdown code fences if present
        text = response_text.strip()
        if text.startswith('```'):
            # Remove first line (```json or ```)
            lines = text.split('\n')
            if lines[0].startswith('```'):
                lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            text = '\n'.join(lines)

        # Parse JSON
        return json.loads(text)

    def plan_auto_images(
        self,
        script_text: str,
        style: Dict,
        n_images: int,
        force_regenerate: bool = False,
        verbose: bool = True
    ) -> AutoImagesPlan:
        """
        Plan auto-generated images using Gemini Director

        Args:
            script_text: Full script text
            style: Style configuration dict with 'id', 'name', 'description'
            n_images: Number of images to generate
            force_regenerate: Skip cache and regenerate
            verbose: Print progress

        Returns:
            AutoImagesPlan with validated scenes

        Raises:
            ValueError: If generation fails or JSON is invalid
        """

        if verbose:
            print(f"\n🎬 GEMINI DIRECTOR (Separate Instance)")
            print(f"   Style: {style.get('name', 'Cinematic')}")
            print(f"   Target: {n_images} images")

        # Check cache
        cache_key = self._get_cache_key(script_text, style, n_images)

        if not force_regenerate:
            cached_plan = self._load_cached_plan(cache_key)
            if cached_plan:
                if verbose:
                    print(f"   ✅ Loaded from cache")
                return cached_plan

        # Generate plan
        if verbose:
            print(f"   🔄 Generating new plan...")

        prompt = self._build_director_prompt(script_text, style, n_images)

        # Try up to 3 times (initial + 2 retries)
        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                start_time = time.time()

                # Call Gemini Director
                response = self.model.generate_content(prompt)
                response_text = response.text

                elapsed = time.time() - start_time

                if verbose:
                    print(f"   ⏱️ Generation: {elapsed:.1f}s (attempt {attempt + 1})")

                # Parse JSON
                try:
                    plan_data = self._parse_json_response(response_text)
                except json.JSONDecodeError as e:
                    if verbose:
                        print(f"   ❌ JSON parse error: {e}")

                    # If not last attempt, retry with fix prompt
                    if attempt < max_attempts - 1:
                        if verbose:
                            print(f"   🔄 Retrying with JSON fix prompt...")
                        prompt = f"""The previous response was not valid JSON.

OUTPUT MUST BE VALID JSON ONLY. NO MARKDOWN FENCES. NO EXPLANATION.

Fix this and return valid JSON:
{response_text}

Return only the corrected JSON."""
                        continue
                    else:
                        raise ValueError(f"Failed to parse JSON after {max_attempts} attempts: {e}")

                # Validate with Pydantic
                try:
                    plan = AutoImagesPlan(**plan_data)

                    if verbose:
                        print(f"   ✅ Plan validated: {len(plan.scenes)} scenes")

                    # Save to cache
                    self._save_cached_plan(cache_key, plan)

                    return plan

                except ValidationError as e:
                    if verbose:
                        print(f"   ❌ Validation error: {e}")

                    # If not last attempt, retry with validation fix prompt
                    if attempt < max_attempts - 1:
                        if verbose:
                            print(f"   🔄 Retrying with validation fix...")

                        error_details = str(e)
                        prompt = f"""The previous response had validation errors:

{error_details}

CRITICAL REQUIREMENTS:
1. scenes array must have EXACTLY {n_images} items
2. scene_id must be 1, 2, 3, ... {n_images} (sequential)
3. Each image_prompt must be detailed (50+ characters)
4. Each field must match the schema

OUTPUT VALID JSON ONLY. NO MARKDOWN.

Fix the previous response:
{response_text}"""
                        continue
                    else:
                        raise ValueError(f"Validation failed after {max_attempts} attempts: {e}")

            except Exception as e:
                last_error = e
                if verbose:
                    print(f"   ❌ Error: {e}")

                if attempt < max_attempts - 1:
                    if verbose:
                        print(f"   🔄 Retrying...")
                    time.sleep(1)
                    continue

        # All attempts failed
        raise ValueError(f"Failed to generate plan after {max_attempts} attempts. Last error: {last_error}")

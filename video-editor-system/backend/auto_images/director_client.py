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

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash"):
        """
        Initialize Director Gemini client

        Args:
            api_key: SEPARATE Gemini API key for Director (not script writer!)
            model_name: Gemini model to use
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

        prompt = f"""You are an AI Director planning visual scenes for a video.

TASK: Create {n_images} image generation prompts from this script.

SCRIPT:
{script_text}

STYLE: {style_name}
{style_description}

REQUIREMENTS:
1. Generate EXACTLY {n_images} scenes
2. Scenes must be CHRONOLOGICAL (beginning → end of script)
3. Each scene must cover a DISTINCT part of the story
4. NO repetition - each scene is unique

PROMPT QUALITY RULES (MANDATORY):
Each image_prompt MUST include:
- Subject (who/what is in the scene)
- Setting/environment (where)
- Action or moment (what's happening)
- Camera/composition (wide shot, close-up, angle)
- Lighting (natural, dramatic, soft, etc.)
- Style tokens: {style_name}, cinematic, high quality
- Color palette guidance

SCENE DISTRIBUTION:
- If N is small (5-10): Cover major story beats
- If N is large (20-70): More granular, still chronological

NEGATIVE PROMPT RULES:
Include in negative_prompt:
- Low quality, blurry, distorted
- Text, watermarks, signatures
- Multiple subjects if script shows one person
- Style-inappropriate elements

OUTPUT FORMAT (STRICT JSON - NO MARKDOWN):
{{
  "mode": "auto_images",
  "style_id": "{style.get('id', 'cinematic')}",
  "n_images": {n_images},
  "global_style_bible": {{
    "style_name": "{style_name}",
    "visual_rules": [
      "Rule 1: ...",
      "Rule 2: ...",
      "Rule 3: ..."
    ],
    "negative_rules": [
      "Avoid: ...",
      "Never: ..."
    ],
    "composition": "Overall composition approach",
    "lighting": "Lighting style",
    "color_palette": ["color1", "color2", "color3"]
  }},
  "scenes": [
    {{
      "scene_id": 1,
      "scene_summary": "Brief description of what happens",
      "narration_focus": "What the script talks about here",
      "keywords": ["keyword1", "keyword2", "keyword3"],
      "image_prompt": "Detailed prompt with subject, setting, action, camera angle, lighting, {style_name} style, high quality, cinematic",
      "negative_prompt": "low quality, blurry, distorted, text, watermarks"
    }},
    ... (exactly {n_images} scenes total)
  ]
}}

SELF-CHECK BEFORE OUTPUTTING:
✓ Number of scenes = {n_images}?
✓ Scenes are chronological through the script?
✓ Each scene is distinct (no repetition)?
✓ Each image_prompt includes: subject, setting, action, camera, lighting, style?
✓ Style rules applied consistently?

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

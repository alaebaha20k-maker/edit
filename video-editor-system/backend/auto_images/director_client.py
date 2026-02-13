"""
Gemini Director Client - Separate Gemini instance for image planning
CRITICAL: Uses SEPARATE credentials from script writer Gemini
"""

import os
import json
import hashlib
import time
from pathlib import Path
from typing import Dict, Optional, List
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
            json.dump(plan.model_dump(), f, indent=2)

    def _build_director_prompt(self, script_text: str, style: Dict, n_images: int, scene_timing_hints: Optional[List[Dict]] = None) -> str:
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
        negative_rules_joined = ', '.join(negative_rules)  # For use in prompts

        # Build timing hints section if provided
        timing_section = ""
        if scene_timing_hints:
            timing_lines = []
            for hint in scene_timing_hints:
                text_preview = hint['text_content'][:100]
                line = f"Scene {hint['scene_id']}: {hint['start_time']:.1f}s - {hint['end_time']:.1f}s ({hint['duration']:.1f}s)\n   Voice says: \"{text_preview}...\""
                timing_lines.append(line)
            timing_hints_text = '\n'.join(timing_lines)
            timing_section = f'''

═══════════════════════════════════════════════════════════
WHISPER STT TIMING (PERFECT SYNC WITH VOICE)
═══════════════════════════════════════════════════════════
CRITICAL: Use these EXACT time windows from voice transcription.
Each scene MUST match the text spoken during that time window.

{timing_hints_text}

IMPORTANT:
- Each image_prompt must describe what's happening during that EXACT time window
- Match visual concept to the text content spoken in that scene
- The narration_focus field should contain the text from that time window
- This ensures PERFECT synchronization between voice and images
═══════════════════════════════════════════════════════════'''

        prompt = f"""You are an AI Director planning visual scenes for a video. You MUST create HIGHLY DETAILED, PROFESSIONAL QUALITY prompts that EXACTLY match the chosen style.

TASK: Create {n_images} DETAILED image generation prompts from this script.

IMPORTANT - MULTILINGUAL SUPPORT:
- The script may be in ANY language (English, Arabic, French, Spanish, Chinese, etc.)
- You MUST understand the script content in its original language
- BUT: ALL image prompts MUST be written in ENGLISH (for optimal image generation quality)
- Translate/adapt the visual concepts while keeping cultural and contextual accuracy

SCRIPT:
{script_text}{timing_section}

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
5. Each prompt MUST be 300+ CHARACTERS (not words!) with EXTREME DETAIL
6. Focus on VISUAL STORYTELLING - create images that tell the story without text

═══════════════════════════════════════════════════════════
CREATIVE SCENE PRINCIPLES - HOW TO CREATE GREAT VISUALS
═══════════════════════════════════════════════════════════

🎨 VISUAL STORYTELLING MASTERY:

1. SHOW, DON'T TELL
   - Instead of "person looking sad" → "woman in her 30s with red-rimmed eyes and tear-stained cheeks, shoulders slumped, staring blankly at an empty coffee cup on a rain-streaked window sill"
   - Instead of "office workspace" → "cluttered mahogany desk with scattered papers, overflowing inbox, cold half-finished coffee, and a framed photo face-down, illuminated by harsh fluorescent overhead lights"

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
   - Golden hour (sunrise/sunset): Warmth, hope, nostalgia, romance
   - Blue hour (twilight): Mystery, contemplation, transition, melancholy
   - Harsh noon sun: Clarity, exposure, harsh reality, intensity
   - Soft overcast: Calm, neutral, introspective, gentle
   - Dramatic side lighting: Tension, conflict, duality, revelation
   - Backlight/rim light: Heroic, ethereal, mysterious, dramatic

5. COLOR PSYCHOLOGY FOR MOOD
   - Warm tones (red, orange, yellow): Energy, passion, urgency, excitement
   - Cool tones (blue, cyan, teal): Calm, technology, sadness, distance
   - Desaturated/muted: Serious, documentary, realistic, somber
   - High saturation: Vibrant, energetic, artificial, stylized
   - Complementary colors: Visual tension and energy (blue/orange, purple/yellow)

6. MATCH SCENES TO SCRIPT CONTENT TYPE
   - Educational/Tutorial content → Clean, bright, organized visuals with clear focus
   - Dramatic/Story content → Cinematic lighting, emotional expressions, narrative moments
   - Tech/Business content → Modern, sleek, professional environments with cool tones
   - Nature/Travel content → Epic landscapes, golden hour lighting, sense of scale
   - Personal/Vlog content → Intimate framing, warm tones, relatable settings

7. CAMERA ANGLE PSYCHOLOGY
   - Eye level: Neutral, relatable, documentary style
   - Low angle (looking up): Power, dominance, heroic, impressive
   - High angle (looking down): Vulnerability, weakness, overview, context
   - Dutch angle (tilted): Unease, tension, disorientation, chaos
   - Over-shoulder: Conversation, involvement, perspective
   - Bird's eye view: Scale, pattern, planning, god's perspective

8. DEPTH OF FIELD STORYTELLING
   - Shallow (blurred background): Focus on subject, intimacy, isolation from surroundings
   - Deep (everything sharp): Context importance, environment as character, documentary feel
   - Rack focus: Shift attention, reveal, dramatic moment

9. VISUAL METAPHORS AND SYMBOLISM
   - Weather matches emotion: Storm = turmoil, sunshine = happiness, fog = confusion
   - Objects tell stories: Wilted flower = lost hope, rising smoke = fleeting time
   - Positioning shows relationships: Close = connection, separated = distance
   - Height in frame = status/power dynamics

10. PROFESSIONAL POLISH
    - Specific materials and textures: "brushed aluminum MacBook", "weathered leather chair", "glossy marble countertop"
    - Exact time of day: "early morning mist at 6am", "golden hour at 7:30pm", "harsh midday sun"
    - Precise clothing details: "navy blue suit with white pocket square", "faded denim jacket with rolled sleeves"
    - Technical camera terms: "85mm lens with f/1.4 aperture", "35mm wide angle", "macro close-up"

═══════════════════════════════════════════════════════════

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

EXAMPLE OF EXCELLENT PROMPT (300+ characters, extreme detail - THIS IS THE STANDARD):
"A determined young trader in his late 20s with short dark hair, intense brown eyes, and deeply focused expression showing slight tension in his jaw, wearing a perfectly pressed crisp white shirt with rolled-up sleeves revealing a silver watch, sitting at a modern minimalist glass desk with brushed steel legs in a sleek corner office featuring floor-to-ceiling windows overlooking a golden-hour city skyline with skyscrapers bathed in warm orange light, leaning forward with both hands gripping the edge of the desk while studying three large glowing 27-inch monitors displaying colorful candlestick trading charts with red and green bars and flowing data streams, medium close-up shot from a 45-degree side angle capturing both his concentrated face profile and the illuminated screens reflection in his eyes, warm golden sunlight at 7pm streaming through the tall windows creating dramatic rim lighting that outlines his profile and shoulders while cool blue-teal monitor glow illuminates his face from the front creating a striking color contrast, {style_name} style, shot with 50mm lens at f/2.8 creating shallow depth of field with razor-sharp focus on subject's face and hands while the background city lights blur into soft bokeh orbs, rich color palette of warm golds and oranges mixing with cool blues and teals, professional photography, high resolution 8k quality, cinematic lighting, sharp details on fabric texture and screen reflections, photorealistic, masterpiece quality"

EXAMPLE OF BAD PROMPT (DO NOT DO THIS):
"Trader at desk looking at computer, {style_name} style"

Each "negative_prompt" MUST include:
- All negative rules from style bible
- Generic quality issues: "low quality, blurry, distorted, pixelated, jpeg artifacts"
- Technical issues: "overexposed, underexposed, bad lighting, poor composition"
- Unwanted elements: "text, watermarks, signatures, logos, banners"
- Style violations: Elements that contradict the chosen style

SCENE DISTRIBUTION STRATEGY:
- If N = 1: ONLY the very first/opening scene that introduces the topic
- If N = 2: Opening scene + final/conclusion scene
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
      "image_prompt": "EXTREMELY DETAILED 300+ CHARACTER PROMPT including: specific subject details (age, features, clothing, expression, body language), precise setting description (location type, time of day, environmental elements, atmosphere), exact action/moment captured (pose, movement, interaction, emotion), specific camera technique (shot type, angle, lens, depth of field), detailed lighting matching {lighting_style} (direction, quality, color temperature, mood), composition matching {composition_style} (framing, rule of thirds, leading lines), {style_name} style elements, color palette using {color_palette_text} with color psychology, professional photography terms (high resolution, 8k, sharp focus, cinematic), material and texture details (fabric, surfaces, reflections), and visual storytelling principles that match the script's content type and emotional tone",
      "negative_prompt": "low quality, blurry, distorted, pixelated, jpeg artifacts, overexposed, underexposed, bad lighting, poor composition, text, watermarks, signatures, {negative_rules_joined}"
    }},
    ... (exactly {n_images} scenes total)
  ]
}}

MANDATORY SELF-CHECK BEFORE OUTPUTTING:
✓ Number of scenes = {n_images} EXACTLY?
✓ Scenes are chronological from start to end of script?
✓ Each scene is completely unique (no repetition)?
✓ Each image_prompt is 300+ CHARACTERS with EXTREME detail?
✓ ALL image_prompt text is in ENGLISH (regardless of script language)?
✓ Cultural context from original script is preserved in visual descriptions?
✓ Each image_prompt applies CREATIVE SCENE PRINCIPLES (show don't tell, emotional depth, cinematic composition)?
✓ Each image_prompt includes: specific subject details, precise setting, exact action/moment, camera technique, detailed lighting, composition, style tokens, color psychology, professional photography terms?
✓ Prompts match the script's CONTENT TYPE (educational/dramatic/tech/nature/personal)?
✓ All visual rules from style bible applied consistently?
✓ All negative rules from style bible included in negative_prompts?
✓ Lighting matches: {lighting_style}?
✓ Composition matches: {composition_style}?
✓ Color palette uses: {color_palette_text}?
✓ Visual storytelling creates EMOTION and ATMOSPHERE, not just descriptions?

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

    def _plan_auto_images_chunked(
        self,
        script_text: str,
        style: Dict,
        n_images: int,
        force_regenerate: bool = False,
        verbose: bool = True
    ) -> AutoImagesPlan:
        """
        Plan auto-images using chunking strategy for large n_images
        Splits into chunks of 20 to avoid rate limits and large responses
        """
        CHUNK_SIZE = 20
        chunks_needed = (n_images + CHUNK_SIZE - 1) // CHUNK_SIZE  # Ceiling division

        if verbose:
            print(f"   📦 Splitting into {chunks_needed} chunks of ~{CHUNK_SIZE} images each")

        all_scenes = []
        scenes_generated = 0

        for chunk_idx in range(chunks_needed):
            # Calculate how many images for this chunk
            remaining = n_images - scenes_generated
            chunk_size = min(CHUNK_SIZE, remaining)

            if verbose:
                print(f"\n   📦 Chunk {chunk_idx + 1}/{chunks_needed}: Generating {chunk_size} images ({scenes_generated + 1}-{scenes_generated + chunk_size})")

            # Split script proportionally
            # For example, if total n_images = 50 and chunk_size = 20:
            # Chunk 1: scenes 1-20 = first 40% of script
            # Chunk 2: scenes 21-40 = next 40% of script
            # Chunk 3: scenes 41-50 = last 20% of script

            script_words = script_text.split()
            total_words = len(script_words)

            start_ratio = scenes_generated / n_images
            end_ratio = (scenes_generated + chunk_size) / n_images

            start_word_idx = int(start_ratio * total_words)
            end_word_idx = int(end_ratio * total_words)

            chunk_script = ' '.join(script_words[start_word_idx:end_word_idx])

            # Generate chunk plan
            chunk_prompt = self._build_director_prompt(chunk_script, style, chunk_size)

            # Add context about chunk position
            chunk_context = f"""
IMPORTANT: This is chunk {chunk_idx + 1} of {chunks_needed}.
Scene IDs should start from {scenes_generated + 1} and end at {scenes_generated + chunk_size}.
This chunk covers scenes {scenes_generated + 1} to {scenes_generated + chunk_size} out of {n_images} total.
"""
            chunk_prompt = chunk_context + chunk_prompt

            # Generate with retries
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    start_time = time.time()
                    response = self.model.generate_content(chunk_prompt)
                    response_text = response.text
                    elapsed = time.time() - start_time

                    if verbose:
                        print(f"      ⏱️ Generation: {elapsed:.1f}s (attempt {attempt + 1})")

                    # Parse JSON
                    plan_data = self._parse_json_response(response_text)

                    # Validate chunk
                    chunk_plan = AutoImagesPlan(**plan_data)

                    # Add scenes to collection
                    all_scenes.extend(chunk_plan.scenes)
                    scenes_generated += len(chunk_plan.scenes)

                    if verbose:
                        print(f"      ✅ Chunk validated: {len(chunk_plan.scenes)} scenes")

                    # Small delay between chunks to avoid rate limits
                    if chunk_idx < chunks_needed - 1:
                        time.sleep(1)

                    break  # Success, exit retry loop

                except (json.JSONDecodeError, ValidationError) as e:
                    if attempt < max_attempts - 1:
                        if verbose:
                            print(f"      ❌ Error: {e}. Retrying...")
                        continue
                    else:
                        raise ValueError(f"Chunk {chunk_idx + 1} failed after {max_attempts} attempts: {e}")

        # Combine all chunks into final plan
        if verbose:
            print(f"\n   ✅ All chunks complete: {len(all_scenes)} total scenes")

        # Create final plan
        final_plan_data = {
            "mode": "auto_images",
            "style_id": style.get('id', 'cinematic'),
            "n_images": n_images,
            "global_style_bible": {
                "style_name": style.get('name', 'Cinematic'),
                "visual_rules": style.get('visual_rules', []),
                "negative_rules": style.get('negative_rules', []),
                "composition": style.get('composition', 'Professional composition'),
                "lighting": style.get('lighting', 'Dramatic lighting'),
                "color_palette": style.get('color_palette', ['Rich colors'])
            },
            "scenes": [scene.model_dump() for scene in all_scenes]
        }

        final_plan = AutoImagesPlan(**final_plan_data)

        # Cache the final plan
        cache_key = self._get_cache_key(script_text, style, n_images)
        self._save_cached_plan(cache_key, final_plan)

        return final_plan

    def plan_avatar_images(
        self,
        script_text: str,
        style: Dict,
        audio_duration_seconds: float,
        force_regenerate: bool = False,
        verbose: bool = True
    ) -> "AutoImagesPlan":
        """
        Plan images for Avatar Auto mode.

        FORMULA: 1 image per minute of audio.
        Example: 30-min audio → 30 images, each placed for ~10 sec every ~60 sec.

        Args:
            script_text: Full video script (used to plan relevant visuals)
            style: Style configuration dict with 'id', 'name', 'visual_rules', etc.
            audio_duration_seconds: Total audio length in seconds (from ffprobe)
            force_regenerate: Skip cache
            verbose: Print progress

        Returns:
            AutoImagesPlan with 400+ char prompts, one scene per minute
        """
        # 1 image per minute (minimum 1)
        n_images = max(1, round(audio_duration_seconds / 60))

        if verbose:
            mins = audio_duration_seconds / 60
            print(f"\n🎬 AVATAR IMAGE PLANNER")
            print(f"   Audio: {mins:.1f} min → {n_images} images (1 per minute)")
            print(f"   Style: {style.get('name', 'Cinematic')}")

        # Build a specialised prompt that tells Gemini about the avatar pattern
        style_name = style.get('name', 'Cinematic')
        style_description = style.get('description', 'High-quality cinematic style')
        visual_rules = style.get('visual_rules', [])
        negative_rules = style.get('negative_rules', [])
        composition_style = style.get('composition', 'Professional composition')
        lighting_style = style.get('lighting', 'Dramatic lighting')
        color_palette = style.get('color_palette', ['Rich colors'])

        visual_rules_text = '\n'.join([f"   - {r}" for r in visual_rules])
        negative_rules_text = '\n'.join([f"   - {r}" for r in negative_rules])
        color_palette_text = ', '.join(color_palette)
        negative_rules_joined = ', '.join(negative_rules)

        minutes_list = '\n'.join(
            [f"  Minute {i+1}: covers script section {i+1}/{n_images}" for i in range(min(n_images, 10))]
        )
        if n_images > 10:
            minutes_list += f"\n  ... (up to minute {n_images})"

        avatar_prompt = f"""You are an elite AI Video Director planning FULL-QUALITY cinematic images for an AVATAR VIDEO.

CONTEXT:
- The video alternates between: [50 sec AVATAR talking] → [10 sec BEAUTIFUL IMAGE] → repeat
- Total audio length: {audio_duration_seconds:.0f} seconds ({audio_duration_seconds/60:.1f} minutes)
- We need EXACTLY {n_images} images (one per minute of video)
- Each image is displayed for ~10 seconds at full screen in front of a professional audience

SCRIPT (analyze the FULL content to plan images that match what is being said):
{script_text}

STYLE BIBLE: {style_name}
Description: {style_description}

VISUAL RULES (MUST FOLLOW):
{visual_rules_text}

NEGATIVE RULES (MUST AVOID):
{negative_rules_text}

Composition: {composition_style}
Lighting: {lighting_style}
Color Palette: {color_palette_text}

DISTRIBUTION PLAN:
{minutes_list}

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {n_images} scenes
2. Each scene covers 1 minute of the script (chronological order)
3. Each "image_prompt" MUST be 400+ CHARACTERS with extreme visual detail
4. Prompts MUST be in ENGLISH regardless of the script language
5. EVERY prompt MUST match the {style_name} style exactly
6. Images will be shown FULL SCREEN - make them STUNNING and CINEMATIC

PROMPT QUALITY STANDARD (400+ chars each, include ALL):
- SUBJECT: Who/what (precise age, appearance, clothing, expression, body language)
- SETTING: Exact location (time of day, weather, environment details, background)
- ACTION: The captured moment (pose, movement, emotion, interaction)
- CAMERA: Shot type + angle + lens focal length + depth of field
- LIGHTING: Detailed lighting setup matching "{lighting_style}"
- COMPOSITION: Framing matching "{composition_style}"
- STYLE TOKEN: "{style_name}" style
- COLOR: Colors from palette ({color_palette_text}) with color psychology purpose
- QUALITY: "professional photography, 8k resolution, sharp focus, ultra-detailed, cinematic"
- TEXTURE: Surface materials, fabric texture, reflections, atmospheric details

OUTPUT (STRICT JSON - NO MARKDOWN, NO EXPLANATION):
{{
  "mode": "auto_images",
  "style_id": "{style.get('id', 'cinematic')}",
  "n_images": {n_images},
  "global_style_bible": {{
    "style_name": "{style_name}",
    "visual_rules": {json.dumps(visual_rules)},
    "negative_rules": {json.dumps(negative_rules)},
    "composition": "{composition_style}",
    "lighting": "{lighting_style}",
    "color_palette": {json.dumps(color_palette)}
  }},
  "scenes": [
    {{
      "scene_id": 1,
      "scene_summary": "Brief description of this minute of the video",
      "narration_focus": "What the script talks about during minute 1",
      "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
      "image_prompt": "EXTREMELY DETAILED 400+ CHARACTER PROMPT — must include subject details, setting, action, camera technique, lighting, composition, style tokens, color palette with psychology, professional photography terms, material/texture details, all matching {style_name} style and the content of the script at that minute",
      "negative_prompt": "low quality, blurry, distorted, pixelated, jpeg artifacts, overexposed, underexposed, bad lighting, poor composition, text, watermarks, logos, {negative_rules_joined}"
    }}
    ... (exactly {n_images} scenes, chronological)
  ]
}}

OUTPUT ONLY VALID JSON."""

        # Use chunking if > 20 images
        if n_images > 20:
            return self._plan_auto_images_chunked(script_text, style, n_images, force_regenerate, verbose)

        # Check cache
        cache_key = self._get_cache_key(script_text + f"|avatar|{audio_duration_seconds:.0f}", style, n_images)
        if not force_regenerate:
            cached = self._load_cached_plan(cache_key)
            if cached:
                if verbose:
                    print(f"   ✅ Loaded from cache ({len(cached.scenes)} scenes)")
                return cached

        # Generate
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                t0 = time.time()
                response = self.model.generate_content(avatar_prompt)
                elapsed = time.time() - t0
                if verbose:
                    print(f"   ⏱️ Gemini response: {elapsed:.1f}s (attempt {attempt+1})")

                plan_data = self._parse_json_response(response.text)
                plan = AutoImagesPlan(**plan_data)

                self._save_cached_plan(cache_key, plan)
                if verbose:
                    print(f"   ✅ Avatar image plan: {len(plan.scenes)} scenes")
                return plan

            except Exception as e:
                if verbose:
                    print(f"   ❌ Attempt {attempt+1} failed: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(1)

        raise ValueError(f"Avatar image planning failed after {max_attempts} attempts")

    def plan_auto_images(
        self,
        script_text: str,
        style: Dict,
        n_images: int,
        scene_timing_hints: Optional[List[Dict]] = None,
        force_regenerate: bool = False,
        verbose: bool = True
    ) -> AutoImagesPlan:
        """
        Plan auto-generated images using Gemini Director
        Uses chunking strategy for large n_images to avoid rate limits

        Args:
            script_text: Full script text
            style: Style configuration dict with 'id', 'name', 'description'
            n_images: Number of images to generate
            scene_timing_hints: Optional list of dicts with timing from Whisper STT
                                [{'scene_id': 1, 'start_time': 0.0, 'end_time': 5.2, 'text_content': '...'}]
            force_regenerate: Skip cache and regenerate
            verbose: Print progress

        Returns:
            AutoImagesPlan with validated scenes

        Raises:
            ValueError: If generation fails or JSON is invalid
        """

        if verbose:
            print(f"\n🎬 GEMINI DIRECTOR (Separate Instance - gemini-2.5-flash)")
            print(f"   Style: {style.get('name', 'Cinematic')}")
            print(f"   Target: {n_images} images")
            if scene_timing_hints:
                print(f"   🎤 Using Whisper timestamps for perfect scene timing")

        # Use chunking strategy for large n_images (> 20)
        if n_images > 20:
            if verbose:
                print(f"   📦 Using chunking strategy (n_images > 20)")
            return self._plan_auto_images_chunked(script_text, style, n_images, force_regenerate, verbose)

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

        prompt = self._build_director_prompt(script_text, style, n_images, scene_timing_hints)

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
3. Each image_prompt must be EXTREMELY detailed (300+ characters MINIMUM)
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

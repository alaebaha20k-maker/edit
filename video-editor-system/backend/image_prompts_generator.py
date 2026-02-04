#!/usr/bin/env python3
"""
Image Prompts Generator for AI Video System
Generate image prompts from script using Gemini + Image Formula
This is the bridge between script and Replicate image generation
"""

import google.generativeai as genai
import re
import time
import os
from pathlib import Path


def generate_image_prompts(script_text, image_formula, count, gemini_api_key, style="", verbose=True):
    """
    Analyze script and generate N image prompts using image formula

    Args:
        script_text: Full script content
        image_formula: User's image style formula from settings
        count: Number of images to generate
        gemini_api_key: Gemini API key
        style: Image style (e.g., "hand draw cartoon", "realistic photo")
        verbose: Print progress

    Returns:
        List of N image prompts
    """

    if verbose:
        print(f"\n🎨 Generating {count} image prompts from script...")
        print(f"   Script length: {len(script_text):,} characters")
        if style:
            print(f"   Style: {style}")

    # Configure Gemini
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Replace {style} placeholder in formula
    if style:
        image_formula = image_formula.replace('{style}', style)
    else:
        image_formula = image_formula.replace('{style}', 'professional, high-quality')

    # PROFESSIONAL CINEMATIC VISUALS PROMPT
    prompt = f"""You are a world-class cinematographer and art director. Your job is to create visual concepts that elevate storytelling.

ASSIGNMENT:
Analyze this script and generate EXACTLY {count} highly specific image search queries that will find perfect visual matches for different narration moments.

IMAGE STYLE FORMULA:
{image_formula}

COMPLETE SCRIPT TO ANALYZE:
{script_text}

═══════════════════════════════════════════════════════════
VISUAL STORYTELLING PRINCIPLES:
═══════════════════════════════════════════════════════════

MOOD MATCHING:
- Identify the emotional tone: urgent, contemplative, triumphant, tense, hopeful
- Match visual mood to narration emotion
- Consider lighting: golden hour = hope, blue hour = mystery, harsh shadows = tension

COMPOSITION PRIORITIES:
- For abstract concepts → Use metaphorical visuals (e.g., "roots" for foundations)
- For action → Dynamic angles, movement, energy
- For data/facts → Clean, organized, professional
- For transformation → Before/after contrast, progression

CINEMATIC QUALITIES:
- Depth of field (shallow for focus, deep for context)
- Color grading direction (warm, cool, desaturated, vibrant)
- Camera angle suggestion (low = powerful, high = vulnerable, eye-level = relatable)

═══════════════════════════════════════════════════════════
SEARCH QUERY CONSTRUCTION:
═══════════════════════════════════════════════════════════

FORMULA:
[Main Subject] + [Action/State] + [Environment] + [Mood/Lighting] + [Quality Modifier]

EXAMPLES:

Script: "Most traders fail because they fight their emotions..."
❌ Weak: "trader stressed"
✅ Strong: "business person contemplating at desk, moody dramatic lighting, cinematic depth of field, professional"

Script: "Singapore engineered a smart nation from nothing..."
❌ Weak: "Singapore city"
✅ Strong: "Singapore Marina Bay skyline at blue hour, futuristic architecture, aerial view, glowing lights, technological feel"

Script: "The lotus grows through mud to bloom..."
❌ Weak: "lotus flower"
✅ Strong: "white lotus emerging from dark muddy water, macro photography, shallow depth of field, golden morning light"

═══════════════════════════════════════════════════════════
QUALITY MODIFIERS (ALWAYS INCLUDE):
═══════════════════════════════════════════════════════════

Choose appropriate modifiers:
- "cinematic" (for dramatic moments)
- "professional" (for business/tech)
- "atmospheric" (for mood-heavy scenes)
- "high detail" (for important visuals)
- "natural lighting" (for authentic feel)
- "golden hour" or "blue hour" (for specific moods)
- "shallow depth of field" (for focus)
- "aerial view" or "wide angle" (for scope)

═══════════════════════════════════════════════════════════
DISTRIBUTION ACROSS SCRIPT:
═══════════════════════════════════════════════════════════

Ensure {count} prompts are evenly distributed:
- Beginning (hook) → 20%
- Early middle (setup) → 20%
- Middle (journey) → 30%
- Late middle (transformation) → 20%
- End (conclusion) → 10%

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {count} prompts (no more, no less)
2. NO TEXT in any images (absolutely forbidden)
3. Each prompt maximum 12-15 words
4. Include "NO TEXT" in each prompt
5. Maintain visual consistency (same style/mood)
6. Extract emotional states and visual metaphors from script

═══════════════════════════════════════════════════════════
OUTPUT FORMAT:
═══════════════════════════════════════════════════════════

Return ONLY numbered search queries. No explanation. Maximum 12-15 words per line.

Example outputs:
1. entrepreneur working late at desk, single desk lamp, determined expression, NO TEXT
2. abstract network connections glowing, dark background, technological visualization, NO TEXT
3. mountain peak sunrise, lone figure silhouette, aspirational, epic landscape, NO TEXT

Generate {count} search queries now:"""

    try:
        # Call Gemini
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.85,
                max_output_tokens=8192,
                top_p=0.92,
                top_k=35
            )
        )

        result_text = response.text.strip()

        if verbose:
            print(f"   ✅ Received response from Gemini")

        # Parse prompts from response
        prompts = parse_prompts_from_response(result_text, count)

        if len(prompts) != count:
            if verbose:
                print(f"   ⚠️ Got {len(prompts)} prompts, expected {count}. Adjusting...")

            # Adjust if needed
            if len(prompts) < count:
                # Duplicate prompts in round-robin fashion
                original_count = len(prompts)
                while len(prompts) < count:
                    # FIX: Use proper round-robin indexing
                    index = (len(prompts) - original_count) % original_count
                    base_prompt = prompts[index]
                    variation = f"{base_prompt}, alternate angle"
                    prompts.append(variation)
            else:
                # Trim excess
                prompts = prompts[:count]

        # Ensure prompts forbid text and specify format
        prompts = ensure_no_text_in_prompts(prompts)

        # Save prompts to file
        prompts_dir = Path(__file__).parent.parent / 'output' / 'prompts'
        prompts_dir.mkdir(parents=True, exist_ok=True)
        prompts_file = prompts_dir / 'image_prompts.txt'

        with open(prompts_file, 'w', encoding='utf-8') as f:
            f.write(f"Generated {count} image prompts\n")
            f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            for i, p in enumerate(prompts, 1):
                f.write(f"PROMPT {i}:\n{p}\n\n")

        if verbose:
            print(f"   ✅ Generated {len(prompts)} prompts")
            print(f"   📄 Saved to: {prompts_file}")

        return prompts

    except Exception as e:
        if verbose:
            print(f"   ❌ Error: {str(e)}")
        raise


def parse_prompts_from_response(text, expected_count):
    """Parse numbered prompts from Gemini response"""

    # Try to find numbered lines
    lines = text.split('\n')
    prompts = []

    current_prompt = ""

    for line in lines:
        line = line.strip()

        # Check if line starts with a number
        if re.match(r'^\d+\.\s+', line):
            # Save previous prompt if exists
            if current_prompt:
                prompts.append(current_prompt.strip())

            # Start new prompt (remove number)
            current_prompt = re.sub(r'^\d+\.\s+', '', line)
        else:
            # Continue current prompt
            if current_prompt:
                current_prompt += " " + line

    # Add last prompt
    if current_prompt:
        prompts.append(current_prompt.strip())

    # Clean prompts
    prompts = [p for p in prompts if len(p) > 50]  # Filter very short ones

    return prompts


def ensure_no_text_in_prompts(prompts):
    """Ensure all prompts explicitly forbid text"""

    cleaned = []
    for prompt in prompts:
        # Make sure "NO TEXT" is explicitly mentioned
        if "NO TEXT" not in prompt.upper():
            prompt += ", NO TEXT in image"

        # Make sure 16:9 and 1080p are mentioned
        if "16:9" not in prompt:
            prompt += ", 16:9 aspect ratio"

        if "1080p" not in prompt:
            prompt += ", 1080p resolution"

        cleaned.append(prompt)

    return cleaned

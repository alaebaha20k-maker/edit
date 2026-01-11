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


def generate_image_prompts(script_text, image_formula, count, gemini_api_key, verbose=True):
    """
    Analyze script and generate N image prompts using image formula

    Args:
        script_text: Full script content
        image_formula: User's image style formula from settings
        count: Number of images to generate
        gemini_api_key: Gemini API key
        verbose: Print progress

    Returns:
        List of N image prompts
    """

    if verbose:
        print(f"\n🎨 Generating {count} image prompts from script...")
        print(f"   Script length: {len(script_text):,} characters")

    # Configure Gemini
    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Build prompt for Gemini
    prompt = f"""You are an expert at creating image prompts for AI image generation.

TASK:
Analyze the provided script and generate EXACTLY {count} distinct image prompts that visually represent different parts of the script.

IMAGE STYLE FORMULA (FOLLOW THIS EXACTLY):
{image_formula}

SCRIPT TO ANALYZE:
{script_text[:10000]}  # Use first 10K chars for analysis

CRITICAL REQUIREMENTS:
1. Generate EXACTLY {count} prompts (no more, no less)
2. Each prompt must follow the Image Style Formula provided above
3. NO TEXT in any images (absolutely forbidden)
4. Always include: 16:9 aspect ratio, 1080p resolution, NO TEXT
5. Distribute prompts across different parts of the script:
   - Beginning (intro/hook)
   - Early middle (problem/setup)
   - Middle (explanation/examples)
   - Late middle (solution/framework)
   - End (implementation/close)
6. Extract emotional states, key concepts, and visual metaphors from script
7. Maintain visual consistency across all prompts (same style, colors, composition)

OUTPUT FORMAT:
Return ONLY the prompts, one per line, numbered.
No explanations, no commentary, just the prompts.

Example format:
1. [First complete prompt here]
2. [Second complete prompt here]
...
{count}. [Last complete prompt here]

Generate {count} prompts now:"""

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
                # Duplicate some prompts with variations
                while len(prompts) < count:
                    base_prompt = prompts[len(prompts) % len(prompts)]
                    prompts.append(base_prompt)  # Simple duplication
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

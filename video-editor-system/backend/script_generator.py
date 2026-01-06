#!/usr/bin/env python3
"""
AI Script Generator using Gemini 2.5 Flash
Generates 60K+ character trading psychology scripts following niche guidelines
"""

import re
import google.generativeai as genai
from typing import Dict, Optional
from config import Config
from niche_manager import NicheManager


class ScriptGenerator:
    """Generate long-form scripts using Gemini 2.5 Flash"""

    def __init__(self):
        """Initialize Gemini API"""
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set. Configure at /api-config.html or set environment variable")

        genai.configure(api_key=api_key)

        # Configure generation settings
        self.generation_config = {
            'temperature': Config.GEMINI_TEMPERATURE,
            'top_p': Config.GEMINI_TOP_P,
            'top_k': Config.GEMINI_TOP_K,
            'max_output_tokens': Config.GEMINI_MAX_TOKENS,
        }

        self.model = genai.GenerativeModel(
            model_name=Config.GEMINI_MODEL,
            generation_config=self.generation_config
        )

    def generate_script(self, title: str, niche_id: str) -> str:
        """
        Generate complete script for video

        Args:
            title: Video title (user-provided)
            niche_id: Niche ID with writing guidelines

        Returns:
            Complete voice-ready script (60K+ characters)
        """
        # Get niche
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        print(f"📝 Generating script for: {title}")
        print(f"   Niche: {niche['name']} ({niche['language']})")

        # Generate script in 3 parts
        opening = self._generate_opening(title, niche)
        print(f"   ✓ Opening: {len(opening)} chars")

        middle = self._generate_middle(title, niche, opening)
        print(f"   ✓ Middle: {len(middle)} chars")

        closing = self._generate_closing(title, niche, opening, middle)
        print(f"   ✓ Closing: {len(closing)} chars")

        # Combine all parts
        full_script = f"{opening}\n\n{middle}\n\n{closing}"

        # Clean for voice-ready output
        full_script = self._clean_for_voice(full_script)

        print(f"   ✅ Total: {len(full_script)} chars")

        # Validate length
        if len(full_script) < Config.MIN_SCRIPT_LENGTH:
            print(f"   ⚠️  Warning: Script shorter than target ({len(full_script)} < {Config.MIN_SCRIPT_LENGTH})")

        return full_script

    def _generate_opening(self, title: str, niche: Dict) -> str:
        """Generate opening section (1/3 of script)"""
        prompt = f"""You are a professional script writer for {niche['name']} videos in {niche['language']}.

TITLE: {title}

WRITING GUIDELINES:
{niche['writing_guidelines']}

YOUR TASK:
Write the OPENING section of a long-form narration script about "{title}".

REQUIREMENTS:
- This is PART 1 of 3 (opening section)
- Target length: 20,000+ characters
- Start with a powerful hook related to the title
- Introduce the main topic and its importance
- Present the core problems or challenges
- Build curiosity and engagement
- Follow ALL writing guidelines above
- Write in {niche['language']}
- VOICE-READY TEXT ONLY (no markdown, no formatting, no asterisks, no bold, no headers)
- Natural speaking rhythm for narration
- Direct, engaging, conversational tone

Write the complete opening section now:"""

        response = self.model.generate_content(prompt)
        return response.text

    def _generate_middle(self, title: str, niche: Dict, opening: str) -> str:
        """Generate middle section (2/3 of script)"""
        # Get summary of opening for context
        opening_summary = opening[:1000] + "..." if len(opening) > 1000 else opening

        prompt = f"""You are continuing a professional script for {niche['name']} videos in {niche['language']}.

TITLE: {title}

OPENING SECTION SUMMARY:
{opening_summary}

WRITING GUIDELINES:
{niche['writing_guidelines']}

YOUR TASK:
Write the MIDDLE section of this long-form narration script.

REQUIREMENTS:
- This is PART 2 of 3 (middle section, continuing from opening)
- Target length: 25,000+ characters
- Develop the main ideas and concepts
- Provide detailed explanations and examples
- Present solutions and strategies
- Include specific scenarios and cases
- Maintain continuity from the opening
- Follow ALL writing guidelines above
- Write in {niche['language']}
- VOICE-READY TEXT ONLY (no markdown, no formatting, no asterisks, no bold, no headers)
- Natural speaking rhythm for narration
- Direct, engaging, conversational tone

Write the complete middle section now:"""

        response = self.model.generate_content(prompt)
        return response.text

    def _generate_closing(self, title: str, niche: Dict, opening: str, middle: str) -> str:
        """Generate closing section (3/3 of script)"""
        # Get summaries for context
        opening_summary = opening[:500] + "..." if len(opening) > 500 else opening
        middle_summary = middle[:1000] + "..." if len(middle) > 1000 else middle

        prompt = f"""You are completing a professional script for {niche['name']} videos in {niche['language']}.

TITLE: {title}

OPENING SUMMARY:
{opening_summary}

MIDDLE SUMMARY:
{middle_summary}

WRITING GUIDELINES:
{niche['writing_guidelines']}

YOUR TASK:
Write the CLOSING section of this long-form narration script.

REQUIREMENTS:
- This is PART 3 of 3 (closing section, wrapping up the script)
- Target length: 15,000+ characters
- Summarize key points covered
- Reinforce main messages
- Provide actionable takeaways
- End with motivational conclusion
- Create satisfying closure
- Maintain continuity with previous sections
- Follow ALL writing guidelines above
- Write in {niche['language']}
- VOICE-READY TEXT ONLY (no markdown, no formatting, no asterisks, no bold, no headers)
- Natural speaking rhythm for narration
- Direct, engaging, conversational tone

Write the complete closing section now:"""

        response = self.model.generate_content(prompt)
        return response.text

    def _clean_for_voice(self, text: str) -> str:
        """Clean text to be voice-ready (remove all markdown and formatting)"""
        # Remove markdown headers
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

        # Remove bold/italic markers
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # Bold+italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)          # Italic
        text = re.sub(r'__(.+?)__', r'\1', text)          # Bold alt
        text = re.sub(r'_(.+?)_', r'\1', text)            # Italic alt

        # Remove markdown lists
        text = re.sub(r'^\s*[\-\*\+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)

        # Remove markdown links
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

        # Remove code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`(.+?)`', r'\1', text)

        # Remove extra whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()

        return text

    def extract_keywords(self, title: str) -> str:
        """Extract keywords from title for image generation"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'of', 'to', 'in', 'for', 'on', 'with', 'is', 'and', 'or'}

        # Split and clean
        words = title.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(keywords[:5])  # Return top 5 keywords


def test_script_generation():
    """Test script generation"""
    print("Testing Script Generator...")

    try:
        # Check API key
        if not Config.GEMINI_API_KEY:
            print("⚠️  GEMINI_API_KEY not set. Set it in environment or config.py")
            print("   Example: export GEMINI_API_KEY='your-api-key'")
            return

        # Create niche manager and get a niche
        from niche_manager import create_default_niches

        print("\nCreating default niches...")
        niches = create_default_niches()

        if not niches:
            print("✗ No niches created")
            return

        niche = niches[0]
        print(f"\nUsing niche: {niche['name']}")

        # Test script generation
        generator = ScriptGenerator()

        test_title = "The Zen Trader's Guide to Emotional Control"
        print(f"\nGenerating script for: {test_title}")

        script = generator.generate_script(test_title, niche['id'])

        print(f"\n✅ Script generated successfully!")
        print(f"   Length: {len(script)} characters")
        print(f"   Preview (first 500 chars):")
        print(f"   {script[:500]}...")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_script_generation()

#!/usr/bin/env python3
"""
Title Generator - Generates clickable video titles using Gemini AI
Uses custom title formulas for different niches
"""

import google.generativeai as genai
from settings_manager import SettingsManager
from niche_manager import NicheManager


class TitleGenerator:
    """Generate engaging video titles using Gemini AI and custom formulas"""

    def __init__(self, gemini_api_key=None):
        """
        Initialize Title Generator

        Args:
            gemini_api_key: Gemini API key (optional - loads from settings if not provided)
        """
        self.api_key = gemini_api_key or SettingsManager.get_api_key('gemini')
        if not self.api_key:
            raise ValueError("Gemini API key not configured. Please set it in Settings.")

        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')

    def generate_title(self, topic, niche_id, count=1, verbose=False):
        """
        Generate video title(s) for a given topic and niche

        Args:
            topic: Topic/subject for the video (e.g., "Jesse Livermore trading psychology")
            niche_id: Niche ID to get language and context
            count: Number of title variations to generate (1-5)
            verbose: Print detailed progress

        Returns:
            Single title string if count=1, or list of titles if count>1

        Example:
            >>> generator = TitleGenerator()
            >>> title = generator.generate_title(
            ...     "Jesse Livermore winning trap",
            ...     niche_id="abc-123",
            ...     count=1
            ... )
            >>> print(title)
            "Transcript of Jesse Livermore | The 'Winning Trap' That Destroyed My Fortune"
        """
        if count < 1 or count > 5:
            raise ValueError("count must be between 1 and 5")

        # Get niche data for context
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        niche_name = niche['name']
        language = niche['language']

        # Load title formula
        title_formula = SettingsManager.load_formula('title')

        # Build the prompt
        prompt = self._build_prompt(
            topic=topic,
            niche_name=niche_name,
            language=language,
            title_formula=title_formula,
            count=count
        )

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎯 GENERATING TITLE")
            print(f"{'='*70}")
            print(f"Topic: {topic}")
            print(f"Niche: {niche_name}")
            print(f"Language: {language}")
            print(f"Count: {count}")
            print(f"{'='*70}\n")

        # Generate with Gemini
        try:
            if verbose:
                print("📡 Calling Gemini API...")

            response = self.model.generate_content(
                prompt,
                generation_config={
                    'temperature': 0.9,  # High creativity for titles
                    'top_p': 0.95,
                    'top_k': 40,
                    'max_output_tokens': 300,
                }
            )

            if verbose:
                print("✅ Response received!")

            # Extract titles from response
            titles = self._parse_titles(response.text, count)

            if verbose:
                print(f"\n📝 Generated {len(titles)} title(s):")
                for i, title in enumerate(titles, 1):
                    print(f"  {i}. {title}")
                print()

            # Return single title or list based on count
            return titles[0] if count == 1 else titles

        except Exception as e:
            if verbose:
                print(f"\n❌ Error generating title: {e}")
            raise

    def _build_prompt(self, topic, niche_name, language, title_formula, count):
        """Build the Gemini prompt using the title formula"""

        # Replace placeholders in formula
        formula_with_topic = title_formula.replace('{topic}', topic)
        formula_with_topic = formula_with_topic.replace('{niche}', niche_name)
        formula_with_topic = formula_with_topic.replace('{language}', language)

        # Add count instruction if multiple titles needed
        if count > 1:
            count_instruction = f"\n\nGenerate {count} different title variations. Output as numbered list:\n1. [first title]\n2. [second title]\netc."
        else:
            count_instruction = "\n\nOutput ONLY the title, nothing else. No quotes, no explanation, just the title text."

        full_prompt = f"""{formula_with_topic}{count_instruction}

CRITICAL RULES:
- Output ONLY the title(s), no additional text
- No quotes around titles
- No "Here's a title:" or similar preamble
- For single title: just output the title directly
- For multiple titles: numbered list only (1. Title, 2. Title, etc.)
- Keep titles between 50-80 characters
- Make them clickable and engaging
- Language: {language}
"""

        return full_prompt

    def _parse_titles(self, response_text, expected_count):
        """
        Parse titles from Gemini response

        Handles both single title and numbered list formats
        """
        lines = response_text.strip().split('\n')
        titles = []

        if expected_count == 1:
            # Single title - just take the first non-empty line
            for line in lines:
                line = line.strip()
                if line and not line.startswith(('Here', 'Title:', '**')):
                    # Clean up any remaining artifacts
                    line = line.strip('"\'*#-')
                    titles.append(line)
                    break
        else:
            # Multiple titles - extract numbered list
            import re
            for line in lines:
                line = line.strip()
                # Match numbered list: "1. Title" or "1) Title" or "1 - Title"
                match = re.match(r'^\d+[\.\)\-\:]\s*(.+)$', line)
                if match:
                    title = match.group(1).strip('"\'*#-')
                    titles.append(title)

        # If parsing failed, return raw response as fallback
        if not titles:
            titles = [response_text.strip().strip('"\'*#-')]

        # Ensure we have the right number of titles
        while len(titles) < expected_count:
            titles.append(titles[0] if titles else "Untitled Video")

        return titles[:expected_count]


def generate_title(topic, niche_id, gemini_api_key=None, count=1, verbose=False):
    """
    Convenience function to generate title without instantiating class

    Args:
        topic: Video topic/subject
        niche_id: Niche UUID
        gemini_api_key: Optional API key (loads from settings if not provided)
        count: Number of titles to generate (1-5)
        verbose: Print progress

    Returns:
        Single title string (if count=1) or list of titles (if count>1)
    """
    generator = TitleGenerator(gemini_api_key=gemini_api_key)
    return generator.generate_title(topic, niche_id, count=count, verbose=verbose)


if __name__ == '__main__':
    # Test the title generator
    print("Testing Title Generator...")

    # You'll need to:
    # 1. Set up Gemini API key in settings
    # 2. Create a niche first
    # Then run this test

    try:
        title = generate_title(
            topic="Jesse Livermore winning trap trading psychology",
            niche_id="your-niche-id-here",  # Replace with actual niche ID
            count=1,
            verbose=True
        )
        print(f"\n✅ Final Title: {title}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nMake sure to:")
        print("1. Configure Gemini API key in Settings")
        print("2. Create a niche first")
        print("3. Replace 'your-niche-id-here' with actual niche ID")

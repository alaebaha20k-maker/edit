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
        """Build the ULTRA-CREATIVE title generation prompt"""

        # Replace placeholders in formula
        formula_with_context = title_formula.replace('{topic}', topic)
        formula_with_context = formula_with_context.replace('{niche}', niche_name)
        formula_with_context = formula_with_context.replace('{language}', language)

        # PROFESSIONAL TITLE GENERATION PROMPT
        if count == 1:
            prompt = f"""You are an elite creative director and viral content strategist with 15 years of experience crafting titles that stop scrollers mid-swipe.

YOUR MISSION:
Generate ONE magnetic, unforgettable title using this exact formula:

{formula_with_context}

CONTEXT:
Niche/Topic: {niche_name}
Language: {language}

QUALITY STANDARDS (NON-NEGOTIABLE):
✓ Must trigger immediate curiosity
✓ Must promise transformation or revelation
✓ Must feel premium, not clickbait
✓ Must be memorable after one read
✓ Must work for both YouTube thumbnail and podcast title
✓ Balance intrigue with clarity
✓ Avoid generic words like "amazing," "incredible," "shocking"
✓ Use power words: Hidden, Forbidden, Ancient, Elite, Silent, Untold

PSYCHOLOGICAL TRIGGERS TO USE:
- Specificity (numbers, timeframes, names)
- Exclusivity (what "they" don't tell you)
- Transformation (before → after state)
- Urgency (without being desperate)
- Authority (insider knowledge)

EXAMPLES OF EXCELLENCE:
❌ BAD: "Amazing Trading Tips You Need"
✅ GOOD: "The 3AM Trade: What Wall Street Doesn't Want Retail Traders to Know"

❌ BAD: "Zombie Movie Ideas"
✅ GOOD: "The Last Harvest: When the Dead Learned to Wait"

❌ BAD: "Singapore Technology"
✅ GOOD: "How Singapore Engineered a Nation with No Natural Resources into a Tech Empire"

OUTPUT FORMAT:
Return ONLY the title. No explanation. No markdown. No quotes. Just raw title text.

Generate now:"""
        else:
            # Multiple titles variation
            prompt = f"""You are an elite creative director and viral content strategist with 15 years of experience crafting titles that stop scrollers mid-swipe.

YOUR MISSION:
Generate {count} DIFFERENT magnetic, unforgettable title variations using this exact formula:

{formula_with_context}

CONTEXT:
Niche/Topic: {niche_name}
Language: {language}

QUALITY STANDARDS (NON-NEGOTIABLE):
✓ Must trigger immediate curiosity
✓ Must promise transformation or revelation
✓ Must feel premium, not clickbait
✓ Must be memorable after one read
✓ Each variation must be DISTINCTLY DIFFERENT in angle/approach
✓ Use power words: Hidden, Forbidden, Ancient, Elite, Silent, Untold

PSYCHOLOGICAL TRIGGERS TO USE:
- Specificity (numbers, timeframes, names)
- Exclusivity (what "they" don't tell you)
- Transformation (before → after state)
- Authority (insider knowledge)

OUTPUT FORMAT:
Return ONLY the numbered list of titles. No explanation. No markdown. No quotes.

Example format:
1. The First Title Goes Here
2. The Second Title Goes Here
3. The Third Title Goes Here

Generate now:"""

        return prompt

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

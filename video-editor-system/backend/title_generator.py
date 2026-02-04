#!/usr/bin/env python3
"""
Title Generator - Generates clickable video titles using Gemini AI
Uses custom title formulas for different niches
"""

import json
import re
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
        self.model = genai.GenerativeModel('gemini-2.5-flash')

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
                    'max_output_tokens': 1500,  # Increased for 10 JSON candidates
                }
            )

            if verbose:
                print("✅ Response received!")
                print(f"📏 Response length: {len(response.text)} chars")

            # Extract titles from response (generates 10, returns best N)
            titles = self._parse_titles(response.text, count)

            if verbose:
                print(f"\n📝 Returning top {len(titles)} title(s) by CTR score:")
                for i, title in enumerate(titles, 1):
                    score = self._score_title(title)
                    print(f"  {i}. [{score}/100] {title}")
                print()

            # Return single title or list based on count
            return titles[0] if count == 1 else titles

        except Exception as e:
            if verbose:
                print(f"\n❌ Error generating title: {e}")
            raise

    def _build_prompt(self, topic, niche_name, language, title_formula, count):
        """Build STRICT JSON prompt - always generate 10 candidates internally"""

        # Replace placeholders in formula
        formula_with_context = title_formula.replace('{topic}', topic)
        formula_with_context = formula_with_context.replace('{niche}', niche_name)
        formula_with_context = formula_with_context.replace('{language}', language)

        # ALWAYS request 10 candidates (we'll rank and return best N)
        prompt = f"""You are an elite creative director and viral content strategist with 15 years of experience crafting titles that stop scrollers mid-swipe.

═══════════════════════════════════════════════════════════
CRITICAL: OUTPUT STRICT JSON ONLY - NO EXPLANATION
═══════════════════════════════════════════════════════════

YOUR MISSION:
Generate 10 HIGH-CTR video title candidates using this EXACT formula:

{formula_with_context}

CONTEXT:
Niche/Topic: {niche_name}
Language: {language}

FORMULA COMPLIANCE (MANDATORY):
✓ FOLLOW THE FORMULA STRUCTURE EXACTLY - word for word
✓ If formula has [Descriptor] + [Noun] + [Location], use THAT structure
✓ If formula provides word lists, USE THOSE EXACT WORDS
✓ If formula shows examples, MATCH THAT STYLE
✓ DO NOT deviate from the formula pattern

YOUTUBE CONSTRAINTS (NON-NEGOTIABLE):
✓ 45-70 characters preferred (max 100)
✓ NO clickbait words: "amazing," "shocking," "incredible," "unbelievable"
✓ NO hashtags in title
✓ NO quotes unless formula explicitly requires them
✓ NO emojis in the title itself

QUALITY STANDARDS:
✓ Trigger immediate curiosity
✓ Promise transformation or revelation
✓ Feel premium, not clickbait
✓ Each candidate must be DISTINCTLY DIFFERENT in angle/approach
✓ Use power words: Hidden, Forbidden, Ancient, Elite, Silent, Untold, Final, Last

PSYCHOLOGICAL ANGLES TO VARY:
- curiosity: Make viewer wonder "what happens?"
- fear: Warn of danger/mistake they're making
- authority: Insider knowledge they don't have
- contrarian: Challenge common beliefs
- story: Personal narrative hook
- how-to: Promise actionable solution
- list: Numbered framework
- myth-busting: Expose lies/misconceptions

OUTPUT JSON SCHEMA (STRICT):
{{
  "titles": [
    {{"title": "exact title text here", "angle": "curiosity", "ctr_score": 85, "why_it_wins": "specific reason in max 12 words"}},
    {{"title": "exact title text here", "angle": "fear", "ctr_score": 82, "why_it_wins": "specific reason in max 12 words"}},
    ...10 total candidates
  ]
}}

EXAMPLES OF EXCELLENCE:
❌ BAD: "Amazing Trading Tips You Need" (generic, clickbait word)
✅ GOOD: "The 3AM Trade: What Wall Street Doesn't Want Retail Traders to Know" (specific, authority angle)

❌ BAD: "Zombie Movie Ideas" (boring)
✅ GOOD: "The Last Harvest of the Dead" (formula-compliant, evocative)

❌ BAD: "Singapore Technology" (vague)
✅ GOOD: "How Singapore Engineered a Tech Empire with No Natural Resources" (contrarian, specific)

RETURN ONLY VALID JSON. NO EXPLANATION. NO MARKDOWN. NO TEXT BEFORE OR AFTER JSON.

Generate 10 candidates now:"""

        return prompt

    def _score_title(self, title):
        """
        Heuristic CTR scoring for titles (0-100)
        Used as fallback when AI doesn't provide ctr_score
        """
        score = 50  # Base score

        # Length scoring (45-70 chars is ideal)
        length = len(title)
        if 45 <= length <= 70:
            score += 15
        elif 35 <= length <= 80:
            score += 10
        elif length > 100:
            score -= 20  # Too long

        # Power words (+2 each, max +10)
        power_words = ['hidden', 'forbidden', 'ancient', 'elite', 'silent', 'untold',
                       'secret', 'final', 'last', 'dead', 'forgotten', 'rising']
        power_count = sum(1 for word in power_words if word.lower() in title.lower())
        score += min(power_count * 2, 10)

        # Specificity: numbers, names, timeframes (+5 each, max +15)
        has_number = bool(re.search(r'\d+', title))
        has_proper_noun = bool(re.search(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)*', title))
        has_timeframe = bool(re.search(r'(dawn|night|day|hour|year|winter|summer|morning)', title.lower()))
        score += (has_number * 5) + (has_proper_noun * 5) + (has_timeframe * 5)

        # Clickbait penalty (-20 for each)
        clickbait = ['amazing', 'shocking', 'incredible', 'unbelievable', 'insane', 'crazy']
        for word in clickbait:
            if word.lower() in title.lower():
                score -= 20

        # Emoji penalty (-30)
        if re.search(r'[✅❌🎯📝💡🔥⚡]', title):
            score -= 30

        # Meta-commentary penalty (-50)
        meta_phrases = ['here are', 'generated:', 'title:', 'based on', 'structure:']
        for phrase in meta_phrases:
            if phrase.lower() in title.lower():
                score -= 50

        # Colon/subtitle bonus (+5)
        if ':' in title or '|' in title:
            score += 5

        # Question bonus (+3)
        if '?' in title:
            score += 3

        return max(0, min(100, score))  # Clamp to 0-100

    def _parse_titles(self, response_text, expected_count):
        """
        Parse titles from Gemini response with STRICT validation

        Priority:
        1. JSON parsing (with 10 candidates ranked by ctr_score)
        2. Strict regex fallback (rejects polluted lines)
        3. Heuristic scoring if ctr_score missing
        """
        candidates = []

        # TRY JSON PARSING FIRST
        try:
            # Extract JSON if wrapped in markdown code blocks
            json_text = response_text.strip()
            if json_text.startswith('```'):
                # Remove markdown code blocks
                json_text = re.sub(r'^```json?\s*\n?', '', json_text)
                json_text = re.sub(r'\n?```\s*$', '', json_text)

            data = json.loads(json_text)

            if 'titles' in data and isinstance(data['titles'], list):
                for item in data['titles']:
                    if isinstance(item, dict) and 'title' in item:
                        title = item['title'].strip()

                        # Validate title quality
                        if self._is_valid_title(title):
                            ctr_score = item.get('ctr_score', self._score_title(title))
                            candidates.append({
                                'title': title,
                                'angle': item.get('angle', 'unknown'),
                                'ctr_score': int(ctr_score),
                                'why_it_wins': item.get('why_it_wins', '')
                            })

                # Sort by CTR score (highest first)
                candidates.sort(key=lambda x: x['ctr_score'], reverse=True)

                # Return best N titles
                return [c['title'] for c in candidates[:expected_count]]

        except (json.JSONDecodeError, KeyError, ValueError):
            # JSON parsing failed - fall back to strict regex
            pass

        # STRICT REGEX FALLBACK
        lines = response_text.strip().split('\n')
        raw_titles = []

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # REJECT polluted lines
            reject_patterns = [
                r'^[✅❌🎯📝💡🔥⚡]',  # Starts with emoji
                r'^(here are|here\'s|generated|title|based on|structure)',  # Meta-commentary
                r'^\*\*',  # Markdown bold
                r'^#+\s',  # Markdown headers
                r':{2,}',  # Multiple colons (not a title)
            ]

            if any(re.search(pattern, line, re.IGNORECASE) for pattern in reject_patterns):
                continue

            # Try to extract numbered list: "1. Title" or "1) Title"
            match = re.match(r'^\d+[\.\)\-\:]\s*(.+)$', line)
            if match:
                title = match.group(1).strip('"\'*#-')
                if self._is_valid_title(title):
                    raw_titles.append(title)
            elif self._is_valid_title(line):
                # Not numbered, but looks like a clean title
                raw_titles.append(line)

        # If we found titles via regex, score and rank them
        if raw_titles:
            for title in raw_titles:
                candidates.append({
                    'title': title,
                    'ctr_score': self._score_title(title)
                })

            candidates.sort(key=lambda x: x['ctr_score'], reverse=True)
            return [c['title'] for c in candidates[:expected_count]]

        # LAST RESORT: Return error message
        return ["ERROR: Could not parse clean titles from AI response"] * expected_count

    def _is_valid_title(self, title):
        """Validate if a string is a clean, usable title"""
        if not title or len(title) < 10:
            return False

        # Reject if contains emojis
        if re.search(r'[✅❌🎯📝💡🔥⚡😀-🙏🚀-🛿]', title):
            return False

        # Reject if contains meta-commentary
        meta_phrases = ['here are', 'generated', 'here is', 'title:', 'based on', 'structure:']
        if any(phrase in title.lower() for phrase in meta_phrases):
            return False

        # Reject if contains markdown formatting
        if re.search(r'(\*\*|__|##|```)', title):
            return False

        # Reject if too long (YouTube limit is ~100 chars)
        if len(title) > 100:
            return False

        return True


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

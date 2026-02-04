#!/usr/bin/env python3
"""
AI Image Generator using Replicate Flux Schnell
Generates 6 images per video with dynamic variable replacement
"""

import re
import replicate
from typing import Dict, List
from config import Config
from image_style_manager import ImageStyleManager


class ImageGenerator:
    """Generate images using Replicate Flux Schnell"""

    def __init__(self):
        """Initialize Replicate API"""
        api_token = Config.get_replicate_api_token()
        if not api_token:
            raise ValueError("REPLICATE_API_TOKEN not set. Configure at /api-config.html or set environment variable")

        # Set API token
        import os
        os.environ['REPLICATE_API_TOKEN'] = api_token

    def generate_images(self, title: str, script: str, style_id: str, count: int = None) -> List[str]:
        """
        Generate images for video with rate limit handling
        For Replicate accounts with < $5 credit: 6 requests per minute max

        Args:
            title: Video title
            script: Generated script text
            style_id: Image style ID with prompt templates
            count: Number of images to generate (default: use all prompts from style)

        Returns:
            List of image URLs (may be less than requested if some fail)
        """
        import time

        # Get image style
        style = ImageStyleManager.get_style(style_id)
        if not style:
            raise ValueError(f"Image style not found: {style_id}")

        # Determine how many images to generate
        max_images = len(style['prompts'])
        if count is None:
            count = max_images
        else:
            count = min(count, max_images)  # Can't generate more than available prompts

        print(f"\n🎨 Generating {count} images")
        print(f"   Style: {style['name']}")

        # CRITICAL: For < $5 accounts, limit is 6 req/min
        # That's 1 request every 10 seconds minimum
        DELAY_BETWEEN_REQUESTS = 11  # 11 seconds = safe margin

        print(f"⏱️  Rate limit mode: {DELAY_BETWEEN_REQUESTS}s delay between images")
        print(f"⏱️  Estimated time: ~{DELAY_BETWEEN_REQUESTS * (count - 1)}s total\n")

        # Extract variables from title and script
        variables = self._extract_variables(title, script)
        print(f"   Variables extracted: {len(variables)} items\n")

        # Generate each image with rate limiting (only generate 'count' images)
        image_urls = []
        for i, prompt_template in enumerate(style['prompts'][:count]):  # Only use first 'count' prompts
            # Replace variables in prompt
            final_prompt = self._replace_variables(prompt_template, variables)

            print(f"🎨 Generating image {i+1}/{count}...")
            print(f"   Prompt: {final_prompt[:80]}...")

            # Generate image with retry logic
            try:
                image_url = self._generate_single_image_with_retry(final_prompt)
                image_urls.append(image_url)
                print(f"   ✅ Generated: {image_url[:60]}...")
            except Exception as e:
                print(f"   ❌ Failed: {str(e)}")
                print(f"   ⚠️  Continuing with remaining images...")

            # Wait between requests to respect rate limit (except after last image)
            if i < count - 1:
                print(f"   ⏳ Waiting {DELAY_BETWEEN_REQUESTS}s before next image...\n")
                time.sleep(DELAY_BETWEEN_REQUESTS)

        print(f"\n✅ Generated {len(image_urls)}/{count} images successfully!")

        if len(image_urls) == 0:
            raise Exception("Failed to generate any images. Please check your Replicate API token and rate limits.")

        return image_urls

    def _generate_single_image_with_retry(self, prompt: str, max_retries: int = 3) -> str:
        """
        Generate single image with retry logic for rate limits

        Args:
            prompt: Image generation prompt
            max_retries: Maximum number of retries for 429 errors

        Returns:
            Image URL
        """
        import time
        import re

        retry_count = 0

        while retry_count < max_retries:
            try:
                return self._generate_single_image(prompt)

            except Exception as e:
                error_str = str(e)

                # Check if it's a rate limit error (429)
                if '429' in error_str or 'throttled' in error_str.lower() or 'rate limit' in error_str.lower():
                    retry_count += 1

                    # Extract wait time from error message
                    match = re.search(r'resets in ~(\d+)s', error_str)
                    wait_time = int(match.group(1)) + 2 if match else 15

                    if retry_count < max_retries:
                        print(f"   ⏳ Rate limit hit! Waiting {wait_time}s (retry {retry_count}/{max_retries})...")
                        time.sleep(wait_time)
                    else:
                        raise Exception(f"Rate limit exceeded after {max_retries} retries. Please wait a minute and try again.")
                else:
                    # Other error - don't retry
                    raise

        raise Exception(f"Failed after {max_retries} retries")

    def _generate_single_image(self, prompt: str) -> str:
        """Generate single image using Replicate"""
        try:
            output = replicate.run(
                Config.REPLICATE_MODEL,
                input={
                    "prompt": prompt,
                    "num_outputs": 1,
                    "aspect_ratio": "16:9",
                    "output_format": "png",
                    "output_quality": 90
                }
            )

            # Handle different output types from Replicate
            # FileOutput objects are iterable but not subscriptable
            if hasattr(output, '__iter__') and not isinstance(output, str):
                # It's iterable (list, generator, or FileOutput iterator)
                try:
                    # Try to get first item
                    for item in output:
                        # Convert to string (URL)
                        return str(item)
                except Exception:
                    pass

            # If it's already a string (URL), return it
            if isinstance(output, str):
                return output

            # Try to convert to string
            try:
                return str(output)
            except Exception:
                raise ValueError(f"Unexpected output format: {type(output).__name__}")

        except Exception as e:
            print(f"     ✗ Error generating image: {e}")
            print(f"     Output type: {type(output).__name__ if 'output' in locals() else 'N/A'}")
            raise

    def _extract_variables(self, title: str, script: str) -> Dict[str, str]:
        """Extract dynamic variables from title and script"""
        variables = {}

        # Extract keywords from title
        variables['{TITLE_KEYWORDS}'] = self._extract_keywords(title)

        # Extract emotional states
        variables['{EMOTIONAL_STATE}'] = self._extract_emotional_state(title, script)

        # Extract chart patterns
        variables['{CHART_PATTERN}'] = self._extract_chart_pattern(script)

        # Extract trading actions
        variables['{TRADING_ACTION}'] = self._extract_trading_action(script)

        # Extract market conditions
        variables['{MARKET_CONDITION}'] = self._extract_market_condition(script)

        # Extract mindset concepts
        variables['{MINDSET_CONCEPT}'] = self._extract_mindset_concept(title, script)

        # Extract psychological terms
        variables['{PSYCHOLOGICAL_TERM}'] = self._extract_psychological_term(script)

        # Extract financial instruments
        variables['{FINANCIAL_INSTRUMENT}'] = self._extract_financial_instrument(script)

        return variables

    def _replace_variables(self, prompt: str, variables: Dict[str, str]) -> str:
        """Replace variables in prompt template"""
        result = prompt

        for variable, value in variables.items():
            if variable in result:
                result = result.replace(variable, value)

        return result

    def _extract_keywords(self, title: str) -> str:
        """Extract keywords from title"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'of', 'to', 'in', 'for', 'on', 'with', 'is', 'and', 'or', 'guide', 'how'}

        # Split and clean
        words = title.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(keywords[:3]) if keywords else 'trading mindset'

    def _extract_emotional_state(self, title: str, script: str) -> str:
        """Extract emotional state from text"""
        emotions = [
            'calm', 'focused', 'disciplined', 'confident', 'patient', 'zen',
            'stressed', 'anxious', 'fearful', 'greedy', 'emotional', 'excited',
            'peaceful', 'balanced', 'controlled', 'composed'
        ]

        # Check title first
        title_lower = title.lower()
        for emotion in emotions:
            if emotion in title_lower:
                return emotion

        # Check script
        script_lower = script.lower()[:2000]  # Check first 2000 chars
        for emotion in emotions:
            if emotion in script_lower:
                return emotion

        return 'calm and focused'

    def _extract_chart_pattern(self, script: str) -> str:
        """Extract chart pattern from script"""
        patterns = [
            'candlestick', 'support and resistance', 'trend line', 'head and shoulders',
            'double top', 'double bottom', 'triangle pattern', 'flag pattern',
            'chart analysis', 'technical pattern', 'price action', 'moving average'
        ]

        script_lower = script.lower()[:3000]
        for pattern in patterns:
            if pattern in script_lower:
                return pattern

        return 'candlestick pattern'

    def _extract_trading_action(self, script: str) -> str:
        """Extract trading action from script"""
        actions = [
            'entering a trade', 'exiting a position', 'taking profit', 'cutting losses',
            'setting stop loss', 'analyzing the market', 'making a decision',
            'executing order', 'managing risk', 'following strategy'
        ]

        script_lower = script.lower()[:3000]
        for action in actions:
            if action in script_lower:
                return action

        return 'analyzing the market'

    def _extract_market_condition(self, script: str) -> str:
        """Extract market condition from script"""
        conditions = [
            'volatile market', 'trending market', 'ranging market', 'bullish market',
            'bearish market', 'sideways market', 'choppy conditions', 'strong trend',
            'market uncertainty', 'high volatility', 'stable market'
        ]

        script_lower = script.lower()[:3000]
        for condition in conditions:
            if condition in script_lower:
                return condition

        return 'volatile market'

    def _extract_mindset_concept(self, title: str, script: str) -> str:
        """Extract mindset concept from text"""
        concepts = [
            'discipline and patience', 'emotional control', 'risk management mindset',
            'trading psychology', 'mental discipline', 'focus and concentration',
            'zen mindset', 'inner peace', 'self control', 'mental clarity',
            'confidence building', 'stress management'
        ]

        # Check title first
        title_lower = title.lower()
        for concept in concepts:
            if concept in title_lower:
                return concept

        # Check script
        script_lower = script.lower()[:3000]
        for concept in concepts:
            if concept in script_lower:
                return concept

        return 'discipline and patience'

    def _extract_psychological_term(self, script: str) -> str:
        """Extract psychological term from script"""
        terms = [
            'emotional control', 'fear and greed', 'cognitive bias', 'mental state',
            'psychological pressure', 'emotional discipline', 'mental strength',
            'trading psychology', 'mindfulness', 'self awareness', 'impulse control'
        ]

        script_lower = script.lower()[:3000]
        for term in terms:
            if term in script_lower:
                return term

        return 'emotional control'

    def _extract_financial_instrument(self, script: str) -> str:
        """Extract financial instrument from script"""
        instruments = [
            'forex', 'stocks', 'cryptocurrency', 'futures', 'options',
            'commodities', 'indices', 'currency pairs', 'equities', 'bonds'
        ]

        script_lower = script.lower()[:3000]
        for instrument in instruments:
            if instrument in script_lower:
                return instrument

        return 'financial markets'


def test_image_generation():
    """Test image generation"""
    print("Testing Image Generator...")

    try:
        # Check API token
        if not Config.REPLICATE_API_TOKEN:
            print("⚠️  REPLICATE_API_TOKEN not set. Set it in environment or config.py")
            print("   Example: export REPLICATE_API_TOKEN='your-token'")
            return

        # Create image style
        from image_style_manager import create_default_styles

        print("\nCreating default styles...")
        styles = create_default_styles()

        if not styles:
            print("✗ No styles created")
            return

        style = styles[0]
        print(f"\nUsing style: {style['name']}")

        # Test image generation
        generator = ImageGenerator()

        test_title = "The Zen Trader's Guide to Emotional Control"
        test_script = """
        Trading psychology is crucial for success in the markets.
        Emotional control and discipline are the foundation of profitable trading.
        When dealing with volatile market conditions, traders must maintain
        their composure and follow their strategy. Fear and greed are the
        biggest enemies of traders. Learning to manage these emotions through
        mindfulness and proper risk management is essential.
        """ * 100  # Make it longer

        print(f"\nGenerating images for: {test_title}")

        image_urls = generator.generate_images(test_title, test_script, style['id'])

        print(f"\n✅ Images generated successfully!")
        print(f"   Count: {len(image_urls)}")
        for i, url in enumerate(image_urls):
            print(f"   Image {i+1}: {url}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_image_generation()

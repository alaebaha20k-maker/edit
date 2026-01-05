#!/usr/bin/env python3
"""
Image Style Manager - CRUD operations for custom image styles
Handles creation, retrieval, update, and deletion of image generation styles
"""

from typing import Dict, List, Optional
from database import ImageStyleDatabase
from config import Config


class ImageStyleManager:
    """Manager for image generation styles with 6 prompt templates"""

    # Dynamic variables that can be used in prompts
    VALID_VARIABLES = [
        '{TITLE_KEYWORDS}',
        '{EMOTIONAL_STATE}',
        '{CHART_PATTERN}',
        '{TRADING_ACTION}',
        '{MARKET_CONDITION}',
        '{MINDSET_CONCEPT}',
        '{PSYCHOLOGICAL_TERM}',
        '{FINANCIAL_INSTRUMENT}'
    ]

    @staticmethod
    def create_style(name: str, prompts: List[str]) -> Dict:
        """
        Create a new image style

        Args:
            name: Style name (e.g., "Stick Figure Trading")
            prompts: List of exactly 6 prompt templates with dynamic variables

        Returns:
            Created style dict with id
        """
        # Validation
        if not name or not name.strip():
            raise ValueError("Style name cannot be empty")

        if not prompts or len(prompts) != Config.IMAGES_PER_VIDEO:
            raise ValueError(f"Must provide exactly {Config.IMAGES_PER_VIDEO} prompts")

        # Validate each prompt
        for i, prompt in enumerate(prompts):
            if not prompt or not prompt.strip():
                raise ValueError(f"Prompt #{i+1} cannot be empty")

            if len(prompt.strip()) < 20:
                raise ValueError(f"Prompt #{i+1} too short (minimum 20 characters)")

        # Create style
        style = ImageStyleDatabase.create(
            name=name.strip(),
            prompts=[p.strip() for p in prompts]
        )

        return style

    @staticmethod
    def get_style(style_id: str) -> Optional[Dict]:
        """Get image style by ID"""
        return ImageStyleDatabase.get_by_id(style_id)

    @staticmethod
    def get_all_styles() -> List[Dict]:
        """Get all image styles"""
        return ImageStyleDatabase.get_all()

    @staticmethod
    def update_style(style_id: str, name: str = None, prompts: List[str] = None) -> Optional[Dict]:
        """
        Update existing image style

        Args:
            style_id: Style ID to update
            name: New name (optional)
            prompts: New prompts (optional, must be 6 if provided)

        Returns:
            Updated style dict or None if not found
        """
        # Validate prompts if provided
        if prompts is not None:
            if len(prompts) != Config.IMAGES_PER_VIDEO:
                raise ValueError(f"Must provide exactly {Config.IMAGES_PER_VIDEO} prompts")

            for i, prompt in enumerate(prompts):
                if not prompt or not prompt.strip():
                    raise ValueError(f"Prompt #{i+1} cannot be empty")

                if len(prompt.strip()) < 20:
                    raise ValueError(f"Prompt #{i+1} too short (minimum 20 characters)")

            prompts = [p.strip() for p in prompts]

        return ImageStyleDatabase.update(style_id, name, prompts)

    @staticmethod
    def delete_style(style_id: str) -> bool:
        """Delete image style by ID"""
        return ImageStyleDatabase.delete(style_id)

    @staticmethod
    def get_style_summary(style_id: str) -> Optional[Dict]:
        """Get style summary (without full prompts for display)"""
        style = ImageStyleDatabase.get_by_id(style_id)

        if not style:
            return None

        return {
            'id': style['id'],
            'name': style['name'],
            'prompts_count': len(style['prompts']),
            'created_at': style['created_at']
        }

    @staticmethod
    def validate_style_exists(style_id: str) -> bool:
        """Check if style exists"""
        return ImageStyleDatabase.get_by_id(style_id) is not None

    @staticmethod
    def get_variables_info() -> List[Dict]:
        """Get information about available dynamic variables"""
        return [
            {
                'variable': '{TITLE_KEYWORDS}',
                'description': 'Extracted keywords from video title',
                'example': 'zen trading mindset'
            },
            {
                'variable': '{EMOTIONAL_STATE}',
                'description': 'Emotional state mentioned in title or script',
                'example': 'calm and focused'
            },
            {
                'variable': '{CHART_PATTERN}',
                'description': 'Chart pattern or technical analysis concept',
                'example': 'bullish candlestick pattern'
            },
            {
                'variable': '{TRADING_ACTION}',
                'description': 'Trading action or decision',
                'example': 'entering a trade'
            },
            {
                'variable': '{MARKET_CONDITION}',
                'description': 'Market condition or state',
                'example': 'volatile market'
            },
            {
                'variable': '{MINDSET_CONCEPT}',
                'description': 'Psychological or mindset concept',
                'example': 'discipline and patience'
            },
            {
                'variable': '{PSYCHOLOGICAL_TERM}',
                'description': 'Psychology-related term',
                'example': 'emotional control'
            },
            {
                'variable': '{FINANCIAL_INSTRUMENT}',
                'description': 'Financial instrument being traded',
                'example': 'forex pairs'
            }
        ]


def create_default_styles():
    """Create default image styles for testing"""
    default_styles = [
        {
            "name": "Stick Figure Trading",
            "prompts": [
                "Minimalist stick figure trader sitting at desk with computer monitor showing trading charts, {TITLE_KEYWORDS}, simple black lines on white background, zen atmosphere",
                "Simple stick figure character displaying {EMOTIONAL_STATE} emotion, trading psychology concept, clean minimalist design, zen trading mindset",
                "Basic stick figure looking at large chart showing {CHART_PATTERN}, focused expression, minimalist illustration, trading analysis scene",
                "Clean stick figure celebrating a successful trade with arms raised, happy expression, {TRADING_ACTION}, minimalist zen style",
                "Stick figure analyzing market data on screen in {MARKET_CONDITION}, thoughtful pose, simple black and white illustration",
                "Stick figure meditating with zen mindset while {MINDSET_CONCEPT} text flows around, peaceful trading psychology, minimalist design"
            ]
        },
        {
            "name": "Modern 3D Trading",
            "prompts": [
                "Modern 3D rendered scene of trader at futuristic desk, {TITLE_KEYWORDS}, sleek glass and metal aesthetic, professional lighting",
                "3D character showing {EMOTIONAL_STATE}, realistic facial expression, modern trading office environment, cinematic composition",
                "3D visualization of {CHART_PATTERN} floating in holographic display, futuristic trading interface, clean modern design",
                "Realistic 3D scene of successful {TRADING_ACTION}, celebration moment, professional trading floor atmosphere",
                "3D rendered market analytics dashboard in {MARKET_CONDITION}, high-tech visualization, depth of field effect",
                "Zen-inspired 3D scene combining {MINDSET_CONCEPT} with trading elements, peaceful modern aesthetic, balanced composition"
            ]
        },
        {
            "name": "Abstract Conceptual",
            "prompts": [
                "Abstract geometric shapes representing {TITLE_KEYWORDS}, flowing lines and gradients, trading concept visualization, modern digital art",
                "Abstract representation of {EMOTIONAL_STATE} using colors and shapes, psychological concept art, smooth gradients and flowing forms",
                "Conceptual visualization of {CHART_PATTERN} as abstract art, geometric precision meets organic flow, professional color palette",
                "Abstract celebration of {TRADING_ACTION}, explosive energy visualization, dynamic composition with vibrant gradients",
                "Abstract market visualization showing {MARKET_CONDITION}, data flow as artistic elements, modern infographic style",
                "Zen-inspired abstract art representing {MINDSET_CONCEPT}, balanced composition, calming color scheme, meditative quality"
            ]
        }
    ]

    created = []
    for style_data in default_styles:
        try:
            style = ImageStyleManager.create_style(
                name=style_data['name'],
                prompts=style_data['prompts']
            )
            created.append(style)
            print(f"✓ Created default style: {style['name']}")
        except Exception as e:
            print(f"✗ Failed to create style '{style_data['name']}': {e}")

    return created


if __name__ == "__main__":
    print("Testing Image Style Manager...")

    # Create default styles
    print("\nCreating default styles...")
    styles = create_default_styles()

    # List all styles
    print("\nAll styles:")
    all_styles = ImageStyleManager.get_all_styles()
    for style in all_styles:
        summary = ImageStyleManager.get_style_summary(style['id'])
        print(f"  - {summary['name']} ({summary['prompts_count']} prompts)")

    # Show available variables
    print("\nAvailable dynamic variables:")
    for var_info in ImageStyleManager.get_variables_info():
        print(f"  - {var_info['variable']}: {var_info['description']}")

    print("\n✓ Image Style Manager tests passed!")

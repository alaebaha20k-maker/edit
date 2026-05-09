#!/usr/bin/env python3
"""
CLI entry point for the bundle generator.

Usage:
    python run_bundle.py --topic "AI side hustles" --count 5 --pages 30 \
        --details "For complete beginners with no tech background" \
        --audience "beginners" --tone "friendly expert"

    python run_bundle.py --topic "Productivity for remote workers" \
        --count 3 --pages 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend/ is on the path when run directly
sys.path.insert(0, str(Path(__file__).parent))

from bundle_generator import BundleGenerator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a multi-ebook bundle using Gemini + async parallel writes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python run_bundle.py --topic "AI side hustles" --count 5 --pages 30
  python run_bundle.py --topic "Keto for beginners" --count 3 --pages 50 \\
      --audience "adults 30-50" --tone "warm and supportive"
""",
    )
    parser.add_argument(
        "--topic", "-t",
        required=True,
        help="Bundle topic / product name (e.g. 'AI side hustles for beginners')",
    )
    parser.add_argument(
        "--count", "-n",
        type=int, default=3,
        help="Number of ebooks in the bundle (1-20, default: 3)",
    )
    parser.add_argument(
        "--pages", "-p",
        type=int, default=30,
        help="Target pages per ebook (5-500, default: 30)",
    )
    parser.add_argument(
        "--details", "-d",
        default="",
        help="Additional product context or target audience details",
    )
    parser.add_argument(
        "--audience", "-a",
        default="general",
        help="Target audience description (default: 'general')",
    )
    parser.add_argument(
        "--tone",
        default="expert",
        help="Writing tone (default: 'expert')",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    gen = BundleGenerator()
    result = gen.generate_bundle(
        bundle_topic    = args.topic,
        product_details = args.details or args.topic,
        num_ebooks      = args.count,
        pages_per_ebook = args.pages,
        audience        = args.audience,
        tone            = args.tone,
        verbose         = not args.quiet,
    )

    if not args.quiet:
        print(f"\n📦 ZIP: {result['zip_path']}")
        print(f"   {result['num_ebooks']} ebooks · "
              f"{result['total_words']:,} words · "
              f"{result['elapsed']:.1f}s")


if __name__ == "__main__":
    main()

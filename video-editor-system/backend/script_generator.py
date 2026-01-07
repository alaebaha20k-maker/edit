#!/usr/bin/env python3
"""
AI Script Generator using Gemini 2.5 Flash - EXACT HTML Reference System
Generates 30K/60K/100K character scripts following niche guidelines
CRITICAL: This matches the HTML reference system EXACTLY
"""

import re
import time
import google.generativeai as genai
from typing import Dict, Optional, List, Tuple
from config import Config
from niche_manager import NicheManager


class ScriptGenerator:
    """Generate long-form scripts using Gemini 2.5 Flash - EXACT HTML system"""

    def __init__(self):
        """Initialize Gemini API with EXACT settings from HTML"""
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set. Configure at /api-config.html or set environment variable")

        genai.configure(api_key=api_key)

        # Model will be created per request with specific temperature
        self.api_key = api_key

    @staticmethod
    def select_narrative_approach(title: str) -> str:
        """
        Detect narrative approach from title - EXACT from HTML selectNarrativeApproach()
        Returns: 'JOURNEY', 'PARADOX', 'PROBLEM_SOLUTION', or 'FRAMEWORK'
        """
        lower_title = title.lower()

        # Journey/Transformation
        if any(word in lower_title for word in ['quit', 'fail', 'journey', 'transformation', 'moment', 'suffer']):
            return 'JOURNEY'

        # Counterintuitive/Paradox
        if (('why' in lower_title or 'celebrating' in lower_title) and
            any(word in lower_title for word in ['but', 'actually', 'lose', 'sounds insane'])):
            return 'PARADOX'

        # Problem/Solution
        if (any(word in lower_title for word in ['stop', 'avoid', 'mistake', '95%']) or
            ('why' in lower_title and 'traders' in lower_title)):
            return 'PROBLEM_SOLUTION'

        return 'FRAMEWORK'

    @staticmethod
    def clean_chunk_artifacts(text: str) -> str:
        """
        EXACT from HTML cleanChunkArtifacts()
        Remove all chunk markers, continue phrases, meta-commentary
        """
        text = re.sub(r'📝 CONTINUE FROM:.*?\n', '', text)
        text = re.sub(r'\*\*CONTINUE.*?\*\*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\*\*BEGIN.*?\*\*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\*\*COMPLETE.*?\*\*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Chunk \d+\/\d+', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Continue seamlessly.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Let me continue.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Continuing from.*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        return text.strip()

    @staticmethod
    def clean_script(text: str) -> str:
        """
        EXACT from HTML cleanScript()
        - Remove chunk artifacts
        - Remove price mentions (CRITICAL)
        - Remove ALL markdown formatting (CRITICAL for voice-ready)
        - Fix spacing
        """
        # Chunk artifacts
        text = re.sub(r'📝.*?CONTINUE.*?\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\*\*CHUNK.*?\*\*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Continue seamlessly.*?\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'Continuing from.*?\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'In the previous section.*?\.', '', text, flags=re.IGNORECASE)
        text = re.sub(r'As we discussed.*?\.', '', text, flags=re.IGNORECASE)
        text = re.sub(r'As mentioned.*?\.', '', text, flags=re.IGNORECASE)

        # Price mentions (CRITICAL)
        text = re.sub(r'\$\d+', '', text)
        text = re.sub(r'\d+\s*dollars?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(price|cost|afford|cheap|expensive|discount|sale)\b', '', text, flags=re.IGNORECASE)

        # Markdown formatting (CRITICAL - voice-ready)
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # Bold+Italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)          # Italic
        text = re.sub(r'__(.+?)__', r'\1', text)          # Bold underscore
        text = re.sub(r'_(.+?)_', r'\1', text)            # Italic underscore
        text = re.sub(r'~~(.+?)~~', r'\1', text)          # Strikethrough
        text = re.sub(r'`(.+?)`', r'\1', text)            # Inline code
        text = re.sub(r'#{1,6}\s+', '', text)             # Headers
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)   # Links
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)  # List bullets
        text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)       # Numbered lists
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)           # Blockquotes

        # Remove remaining asterisks
        text = re.sub(r'\*', '', text)

        # Fix spacing
        text = re.sub(r'\n{4,}', '\n\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()

    @staticmethod
    def validate_quality(script: str) -> Dict:
        """
        EXACT from HTML validateQuality()
        Check for issues and auto-fix when possible
        Return quality score: HIGH, MEDIUM, LOW
        """
        issues = []

        # Check asterisks/markdown
        if re.search(r'\*\*|\*|__', script):
            issues.append('⚠️ Contains markdown - auto-cleaning...')
            script = ScriptGenerator.clean_script(script)

        # Check price mentions (CRITICAL)
        if re.search(r'\$\d+|\d+\s*dollars?|price|cost', script, re.IGNORECASE):
            issues.append('⚠️ CRITICAL: Contains price mention - auto-cleaning...')
            script = re.sub(r'\$\d+', '', script)
            script = re.sub(r'\d+\s*dollars?', '', script, flags=re.IGNORECASE)
            script = re.sub(r'\b(price|cost)\b', '', script, flags=re.IGNORECASE)

        # Check "link in description" count
        link_count = len(re.findall(r'link in (the )?description', script, re.IGNORECASE))
        if link_count < 2:
            issues.append(f'Only {link_count} "link in description" (need 2-3)')
        elif link_count > 3:
            issues.append(f'Too many "link in description": {link_count} (need 2-3)')

        # Check repetitive phrases
        repetitive = ['let me tell you', "here's the thing", 'the truth is']
        for phrase in repetitive:
            count = len(re.findall(phrase, script, re.IGNORECASE))
            if count > 2:
                issues.append(f'Repetitive: "{phrase}" appears {count} times')

        # Quality markers
        has_numbers = bool(re.search(r'\$[\d,]+|\d+%', script))
        has_real_examples = bool(re.search(r'Livermore|Seykota|Tudor Jones|Minervini|O\'Neil', script, re.IGNORECASE))

        if not has_numbers:
            issues.append('Consider adding specific dollar amounts or percentages')
        if not has_real_examples:
            issues.append('Consider adding real examples')

        quality = 'HIGH' if len(issues) == 0 else ('MEDIUM' if len(issues) < 3 else 'LOW')

        return {
            'clean': len(issues) == 0,
            'issues': issues,
            'quality': quality,
            'script': script
        }

    def build_prompt_part_1(self, title: str, niche_data: Dict, target_chars: int) -> str:
        """
        EXACT from HTML buildPrompt1()
        Replace PRODUCT references with niche_data['product']
        Replace trading-specific text with niche_data['integration_style']
        Keep SAME structure, SAME temperature (0.90)
        """
        product = niche_data.get('product', 'our platform')
        integration_style = niche_data.get('integration_style', 'natural product mentions')

        prompt = f"""You are a master script writer creating a voice-ready narration script in {niche_data['language']}.

📝 TITLE: {title}

🎯 TARGET: {target_chars:,} characters for this section (Part 1 of 3)

📚 NICHE GUIDELINES:
{niche_data['writing_guidelines']}

🎬 YOUR TASK - PART 1: HOOK & FRAMEWORK

Write the OPENING section with a powerful hook that:
- Grabs attention in first 10 seconds
- Presents a compelling problem or transformation
- Sets up the framework for deeper exploration
- Builds massive curiosity for what's coming
- Follows narrative approach: {self.select_narrative_approach(title)}

🔥 REFERENCE QUALITY EXAMPLES:
- "I quit my job with $73 in my bank account. Six months later, I pulled $180,000 from the market. But here's what nobody tells you about that moment..."
- "Why do 95% of traders fail? Because they're doing exactly what the professionals want them to do. And I was one of them until..."
- "The moment I stopped trying to predict the market was the moment everything changed. Sounds insane, right? Let me explain..."

💎 PRODUCT INTEGRATION MASTERY:
{integration_style}

Product/Platform: {product}
- Natural mentions ONLY (1-2 times in this section)
- Example: "and I track everything using {product}, link in description"
- NEVER mention price, cost, or affordability
- Seamlessly woven into the narrative

🚫 FORBIDDEN LANGUAGE (AUTO-REJECT IF USED):
- "Let me tell you" (max 1 time)
- "Here's the thing" (max 1 time)
- Any marketing fluff or hype
- Price mentions ($XX, "affordable", "cheap", "expensive")
- "Click the link" or pushy CTAs

✅ QUALITY RULES:
- Maximum 20 words per sentence
- Specific examples with real numbers ($45,000, 73%, etc.)
- Real scenarios, not generic advice
- Conversational but authoritative tone
- NO markdown (no **, *, __, headers, bullets)
- Pure voice-ready text
- Seamless flow between ideas

🎯 EXACT OUTPUT FORMAT:
Write {target_chars:,} characters of pure narration text. Start immediately with the hook. No titles, no sections, no meta-commentary. Just the script.

BEGIN WRITING NOW:"""

        return prompt

    def build_prompt_part_2(self, title: str, niche_data: Dict, previous_ending: str, target_chars: int) -> str:
        """
        EXACT from HTML buildPrompt2()
        Use last 4 sentences from part 1
        Keep SAME structure, SAME temperature (0.85)
        """
        product = niche_data.get('product', 'our platform')
        integration_style = niche_data.get('integration_style', 'natural product mentions')

        prompt = f"""You are continuing a master-level narration script in {niche_data['language']}.

📝 TITLE: {title}

🎯 TARGET: {target_chars:,} characters for this section (Part 2 of 3)

📚 NICHE GUIDELINES:
{niche_data['writing_guidelines']}

📝 CONTINUE FROM (last context):
"{previous_ending}"

🎬 YOUR TASK - PART 2: DEEP INSIGHTS & DEVELOPMENT

Continue seamlessly from above. This middle section should:
- Develop the main concepts in detail
- Provide specific strategies and frameworks
- Include real examples with numbers and scenarios
- Build toward practical implementation
- Maintain the narrative energy

💎 PRODUCT INTEGRATION:
{integration_style}

Product/Platform: {product}
- Natural mentions (1-2 times in this section)
- Example: "I analyze all my setups in {product}, link in description"
- NEVER mention price or cost
- Feel like genuine recommendation

🚫 FORBIDDEN PATTERNS:
- "In the previous section" (NEVER reference structure)
- "As we discussed" (flow should be seamless)
- "Let me continue" (just continue!)
- Price mentions of any kind
- Repetitive phrases

✅ QUALITY STANDARDS:
- Maximum 20 words per sentence
- Concrete examples with real numbers
- Real scenarios and case studies
- Natural conversational flow
- NO markdown formatting
- Voice-ready narration only

🔗 CONTINUITY RULES:
- Start directly from the previous ending
- NO transition phrases about "continuing"
- Seamless flow as if one continuous piece
- Maintain same energy and tone

🎯 EXACT OUTPUT:
Write {target_chars:,} characters continuing seamlessly. No meta-commentary. Just the script.

CONTINUE NOW:"""

        return prompt

    def build_prompt_part_3(self, title: str, niche_data: Dict, previous_ending: str, target_chars: int) -> str:
        """
        EXACT from HTML buildPrompt3()
        Use last 4 sentences from part 2
        Include full CTA template from niche_data['cta_template']
        Keep SAME structure, SAME temperature (0.80)
        """
        product = niche_data.get('product', 'our platform')
        integration_style = niche_data.get('integration_style', 'natural product mentions')
        cta_template = niche_data.get('cta_template', f'If you want to track your progress like I do, check out {product}, link in the description.')

        prompt = f"""You are completing a master-level narration script in {niche_data['language']}.

📝 TITLE: {title}

🎯 TARGET: {target_chars:,} characters for this section (Part 3 of 3 - FINAL)

📚 NICHE GUIDELINES:
{niche_data['writing_guidelines']}

📝 CONTINUE FROM (last context):
"{previous_ending}"

🎬 YOUR TASK - PART 3: IMPLEMENTATION & POWERFUL CLOSE

Continue seamlessly to wrap up with:
- Actionable implementation steps
- Real-world application examples
- Reinforcement of key insights
- Motivational, empowering conclusion
- Natural product mention and CTA

💎 PRODUCT INTEGRATION & CTA:
{integration_style}

Product/Platform: {product}

CTA Template (use naturally near the end):
"{cta_template}"

Also include ONE "link in description" mention earlier in natural context.

🚫 FORBIDDEN IN CLOSING:
- Generic advice without specifics
- "In conclusion" or "to summarize" (just do it naturally)
- Pushy sales language
- Price mentions
- Multiple CTAs (just 1-2 natural mentions)

✅ CLOSING QUALITY:
- Maximum 20 words per sentence
- End with inspiration and empowerment
- Specific final examples or numbers
- Natural flow into CTA
- NO markdown
- Voice-ready only
- Leave viewer motivated and clear on next steps

🔗 SEAMLESS CONTINUATION:
- Start directly from previous ending
- NO meta-commentary about structure
- One continuous narrative flow
- Maintain energy through to powerful end

🎯 EXACT OUTPUT:
Write {target_chars:,} characters to complete the script powerfully. No meta-commentary. Just the script.

COMPLETE NOW:"""

        return prompt

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 60000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate script using EXACT HTML system logic

        Args:
            title: Video title
            niche_id: Niche ID with writing guidelines
            length: 30000, 60000, or 100000 ONLY
            verbose: Print progress

        Returns:
            Dict with script, stats, quality info
        """
        start_time = time.time()

        # Validate length
        if length not in Config.VALID_SCRIPT_LENGTHS:
            raise ValueError(f'Length must be one of {Config.VALID_SCRIPT_LENGTHS}')

        # Get niche
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        if verbose:
            print(f"\n🎬 Generating script: {title}")
            print(f"📏 Target: {length:,} characters")

        # Detect narrative approach (EXACT from HTML)
        approach = self.select_narrative_approach(title)
        if verbose:
            print(f"🧠 Narrative: {approach}")

        # Calculate target per part
        target_per_part = length // 3
        chunks = []

        # PART 1 - Hook & Framework (temp 0.90)
        if verbose:
            print(f"\n🎨 Part 1: Hook & Framework...")

        model_part1 = genai.GenerativeModel('gemini-2.5-flash')
        prompt1 = self.build_prompt_part_1(title, niche, target_per_part)
        response1 = model_part1.generate_content(
            prompt1,
            generation_config=genai.types.GenerationConfig(
                temperature=Config.GEMINI_TEMPERATURE_PART1,  # 0.90
                max_output_tokens=Config.GEMINI_MAX_TOKENS,   # 65536
                top_p=Config.GEMINI_TOP_P,                     # 0.92
                top_k=Config.GEMINI_TOP_K                      # 35
            )
        )
        chunk1 = response1.text.strip()
        chunks.append(chunk1)

        if verbose:
            print(f"✅ Part 1: {len(chunk1):,} chars")

        time.sleep(1.5)  # Rate limit protection

        # PART 2 - Deep Insights (temp 0.85)
        if verbose:
            print(f"\n🎨 Part 2: Deep Insights...")

        # Get last 4 sentences from part 1 (EXACT from HTML)
        sentences = [s.strip() for s in re.split(r'[.!?]', chunk1) if len(s.strip()) > 20]
        previous_ending = '. '.join(sentences[-4:]) + '.' if len(sentences) >= 4 else '. '.join(sentences) + '.'

        model_part2 = genai.GenerativeModel('gemini-2.5-flash')
        prompt2 = self.build_prompt_part_2(title, niche, previous_ending, target_per_part)
        response2 = model_part2.generate_content(
            prompt2,
            generation_config=genai.types.GenerationConfig(
                temperature=Config.GEMINI_TEMPERATURE_PART2,  # 0.85
                max_output_tokens=Config.GEMINI_MAX_TOKENS,
                top_p=Config.GEMINI_TOP_P,
                top_k=Config.GEMINI_TOP_K
            )
        )
        chunk2 = response2.text.strip()
        chunks.append(chunk2)

        if verbose:
            print(f"✅ Part 2: {len(chunk2):,} chars")

        time.sleep(1.5)

        # PART 3 - Implementation & Close (temp 0.80)
        if verbose:
            print(f"\n🎨 Part 3: Implementation & Close...")

        # Get last 4 sentences from part 2
        sentences2 = [s.strip() for s in re.split(r'[.!?]', chunk2) if len(s.strip()) > 20]
        previous_ending2 = '. '.join(sentences2[-4:]) + '.' if len(sentences2) >= 4 else '. '.join(sentences2) + '.'

        model_part3 = genai.GenerativeModel('gemini-2.5-flash')
        prompt3 = self.build_prompt_part_3(title, niche, previous_ending2, target_per_part)
        response3 = model_part3.generate_content(
            prompt3,
            generation_config=genai.types.GenerationConfig(
                temperature=Config.GEMINI_TEMPERATURE_PART3,  # 0.80
                max_output_tokens=Config.GEMINI_MAX_TOKENS,
                top_p=Config.GEMINI_TOP_P,
                top_k=Config.GEMINI_TOP_K
            )
        )
        chunk3 = response3.text.strip()
        chunks.append(chunk3)

        if verbose:
            print(f"✅ Part 3: {len(chunk3):,} chars")

        # Merge and clean (EXACT from HTML)
        if verbose:
            print(f"\n🧹 Creating seamless block...")

        final_script = '\n\n'.join(chunks)
        final_script = self.clean_script(final_script)

        # Validate quality (EXACT from HTML)
        if verbose:
            print(f"\n🔍 Validating quality...")

        validation = self.validate_quality(final_script)
        final_script = validation['script']

        if verbose:
            print(f"\n✅ Quality: {validation['quality']}")
            for issue in validation['issues']:
                print(f"   {issue}")

        elapsed = int(time.time() - start_time)
        stats = {
            'chars': len(final_script),
            'words': len(final_script.split()),
            'time': elapsed,
            'quality': validation['quality']
        }

        if verbose:
            print(f"\n🎉 Complete: {stats['chars']:,} chars in {elapsed}s")

        return {
            'script': final_script,
            'stats': stats,
            'title': title,
            'approach': approach,
            'quality': validation['quality'],
            'issues': validation['issues']
        }

    def extract_keywords(self, title: str) -> str:
        """Extract keywords from title for image generation"""
        # Remove common words
        stop_words = {'the', 'a', 'an', 'of', 'to', 'in', 'for', 'on', 'with', 'is', 'and', 'or'}

        # Split and clean
        words = title.lower().split()
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(keywords[:5])  # Return top 5 keywords


def test_script_generation():
    """Test script generation with EXACT HTML system"""
    print("Testing Script Generator (EXACT HTML System)...")

    try:
        # Check API key
        if not Config.get_gemini_api_key():
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

        test_title = "Why Trading Multiple Setups Keeps You Broke"
        print(f"\nGenerating script for: {test_title}")

        result = generator.generate_script(
            test_title,
            niche['id'],
            length=60000,  # Test 60K length
            verbose=True
        )

        print(f"\n✅ Script generated successfully!")
        print(f"   Length: {result['stats']['chars']} characters")
        print(f"   Words: {result['stats']['words']} words")
        print(f"   Quality: {result['quality']}")
        print(f"   Narrative: {result['approach']}")
        print(f"   Time: {result['stats']['time']}s")
        print(f"\n   Preview (first 500 chars):")
        print(f"   {result['script'][:500]}...")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_script_generation()

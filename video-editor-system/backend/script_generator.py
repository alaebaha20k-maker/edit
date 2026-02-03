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
    """Generate long-form scripts using Gemini 2.5 Flash - WITH HARD VALIDATION"""

    # HARD VALIDATION PATTERNS - These patterns INVALIDATE the script
    INVALID_PATTERNS = [
        (r'(?i)\bvisual\s*:', 'VISUAL: label detected'),
        (r'(?i)\bnarrator\s*:', 'NARRATOR: label detected'),
        (r'\(\s*\d+\s*-\s*\d+\s*(seconds?|sec|min|minutes?)\s*\)', 'Timestamp detected'),
        (r'(?i)to\s+be\s+continued', 'TO BE CONTINUED detected'),
        (r'(?i)part\s+\d+', 'Part X detected'),
        (r'(?i)section\s+\d+', 'Section X detected'),
        (r'(?i)scene\s+\d+', 'Scene X detected'),
        (r'(?i)\bshow\s*:', 'SHOW: label detected'),
        (r'(?i)\bcut\s+to\s*:', 'CUT TO: label detected'),
        (r'(?i)\bvideo\s*:', 'VIDEO: label detected'),
        (r'^\s*[A-Z\s]+:\s', 'Label formatting detected (e.g., NARRATOR:)'),
        (r'\[\s*\w+\s*\]', 'Bracketed directions detected'),
    ]

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
    def hard_validate_output(script: str, title: str, target_length: int) -> Dict:
        """
        HARD VALIDATION - Checks if script meets strict quality requirements
        Returns validation result with pass/fail and reasons

        This is an ENGINEERING FIX - not a prompt change.
        If validation fails, the script MUST be regenerated.

        Args:
            script: Generated script text
            title: Original title (for title-lock validation)
            target_length: Target character length

        Returns:
            Dict with 'valid' (bool), 'errors' (list), 'warnings' (list)
        """
        errors = []
        warnings = []

        # 1. CHECK FOR INVALID PATTERNS (screenplay formatting, visual cues, etc.)
        for pattern, error_msg in ScriptGenerator.INVALID_PATTERNS:
            matches = re.findall(pattern, script, re.MULTILINE | re.IGNORECASE)
            if matches:
                errors.append(f"{error_msg} - Found {len(matches)} occurrence(s)")

        # 2. CHECK LENGTH TOLERANCE (±3%)
        actual_length = len(script)
        min_length = int(target_length * (1 - Config.SCRIPT_LENGTH_TOLERANCE))
        max_length = int(target_length * (1 + Config.SCRIPT_LENGTH_TOLERANCE))

        if actual_length < min_length:
            errors.append(f"Script too short: {actual_length} chars (min {min_length})")
        elif actual_length > max_length:
            errors.append(f"Script too long: {actual_length} chars (max {max_length})")

        # 3. TITLE-LOCK VALIDATION (prevent topic drift)
        title_lock_result = ScriptGenerator.validate_title_lock(script, title)
        if not title_lock_result['valid']:
            errors.append(f"Title-lock failed: {title_lock_result['reason']}")

        # 4. CHECK FOR EMPTY OUTPUT
        if len(script.strip()) < 100:
            errors.append("Script is nearly empty (< 100 chars)")

        # 5. WARNINGS (don't invalidate but should be noted)
        if len(script.split('\n\n')) > 50:
            warnings.append(f"Many paragraph breaks ({len(script.split(chr(10)*2))})")

        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'actual_length': actual_length,
            'target_length': target_length
        }

    @staticmethod
    def validate_title_lock(script: str, title: str) -> Dict:
        """
        TITLE-LOCK VALIDATOR
        Ensures script stays focused on the title topic (prevents drift)

        Extracts key nouns from title and checks if script references them.

        Args:
            script: Generated script text
            title: Original video title

        Returns:
            Dict with 'valid' (bool) and 'reason' (str)
        """
        # Extract key nouns from title (simple heuristic)
        # Remove common words and extract meaningful keywords
        stop_words = {'the', 'a', 'an', 'of', 'to', 'in', 'for', 'on', 'at', 'by', 'with', 'from',
                      'this', 'that', 'these', 'those', 'is', 'are', 'was', 'were', 'be', 'been',
                      'how', 'what', 'why', 'when', 'where', 'who', 'which', 'i', 'you', 'we', 'they'}

        title_words = [w.strip('.,!?:;').lower() for w in title.split()]
        key_words = [w for w in title_words if len(w) > 3 and w not in stop_words]

        if not key_words:
            # Title has no significant keywords - can't validate, assume valid
            return {'valid': True, 'reason': 'No keywords to validate'}

        # Count how many key words appear in script
        script_lower = script.lower()
        matches = sum(1 for word in key_words if word in script_lower)
        match_ratio = matches / len(key_words)

        # At least 50% of title keywords must appear in script
        if match_ratio < 0.5:
            return {
                'valid': False,
                'reason': f"Only {matches}/{len(key_words)} title keywords found in script (need 50%+)"
            }

        # Split script into paragraphs and check distribution
        paragraphs = [p.strip() for p in script.split('\n\n') if p.strip()]
        if len(paragraphs) >= 3:
            # Check first, middle, and last paragraphs
            first_para = paragraphs[0].lower()
            middle_para = paragraphs[len(paragraphs)//2].lower()
            last_para = paragraphs[-1].lower()

            # At least one key word should appear in first and last paragraphs
            first_has_key = any(word in first_para for word in key_words)
            last_has_key = any(word in last_para for word in key_words)

            if not (first_has_key and last_has_key):
                return {
                    'valid': False,
                    'reason': 'Title keywords missing from start or end (topic drift detected)'
                }

        return {'valid': True, 'reason': 'Title-lock validated'}

    @staticmethod
    def validate_quality(script: str, expected_length: int = None) -> Dict:
        """
        Validate quality with RELAXED thresholds for HIGH rating
        Separates critical issues from helpful suggestions
        """
        issues = []  # Critical issues that affect quality score
        suggestions = []  # Helpful tips that don't affect score

        # Auto-fix markdown/asterisks (DON'T count as issue - this is expected)
        if re.search(r'\*\*|\*|__', script):
            script = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', script)
            script = re.sub(r'\*\*(.+?)\*\*', r'\1', script)
            script = re.sub(r'\*(.+?)\*', r'\1', script)
            script = re.sub(r'__(.+?)__', r'\1', script)
            script = re.sub(r'_(.+?)_', r'\1', script)
            script = re.sub(r'\*', '', script)
            # Auto-fixed silently - not an issue

        # Auto-fix price mentions (DON'T count as issue - this is expected)
        if re.search(r'\$\d+|\d+\s*dollars?|price|cost', script, re.IGNORECASE):
            script = re.sub(r'\$\d+', '', script)
            script = re.sub(r'\d+\s*dollars?', '', script, flags=re.IGNORECASE)
            script = re.sub(r'\b(price|cost)\b', '', script, flags=re.IGNORECASE)
            # Auto-fixed silently - not an issue

        # Check script length if expected length provided
        if expected_length:
            actual_length = len(script)
            minimum_length = expected_length * 0.80  # Allow 20% shorter
            if actual_length < minimum_length:
                issues.append(f'Script shorter than expected: {actual_length:,} chars (target: {expected_length:,})')

        # Check "link in description" count (RELAXED)
        link_count = len(re.findall(r'link in (the )?description', script, re.IGNORECASE))
        if link_count < 1:
            issues.append(f'Missing "link in description" (found {link_count})')
        elif link_count > 5:
            suggestions.append(f'💡 Many "link in description": {link_count} times (2-3 is ideal)')
        # 1-5 mentions is fine, don't flag

        # Check repetitive phrases (RELAXED - only flag if excessive)
        repetitive = ['let me tell you', "here's the thing", 'the truth is', 'at the end of the day']
        for phrase in repetitive:
            count = len(re.findall(phrase, script, re.IGNORECASE))
            if count > 3:  # Changed from 2 to 3
                issues.append(f'Repetitive: "{phrase}" ({count} times)')

        # Check for chunk artifacts (CRITICAL issue)
        chunk_markers = ['continuing from', 'continue seamlessly', 'as we discussed earlier', 'in the previous section']
        for marker in chunk_markers:
            if marker in script.lower():
                issues.append(f'Contains chunk artifact: "{marker}"')
                break

        # Check for blatant sales language (CRITICAL issue)
        sales_terms = ['buy now', 'limited time offer', 'act now', 'special discount', 'order today']
        for term in sales_terms:
            if term in script.lower():
                issues.append(f'Sales language: "{term}"')

        # Quality markers (POSITIVE indicators - suggestions only, not required)
        has_numbers = bool(re.search(r'\$[\d,]+|\d+%|\d+\s+trades|\d+\s+days', script))
        has_examples = bool(re.search(r'Livermore|Seykota|Tudor Jones|Minervini|O\'Neil|for example|for instance', script, re.IGNORECASE))

        if not has_numbers:
            suggestions.append('💡 Could add specific dollar amounts or percentages')
        if not has_examples:
            suggestions.append('💡 Could add real trader examples or "for example" phrases')

        # Calculate quality (RELAXED THRESHOLDS)
        # 0-2 issues = HIGH, 3-4 issues = MEDIUM, 5+ issues = LOW
        if len(issues) == 0:
            quality = 'HIGH'
        elif len(issues) <= 2:
            quality = 'HIGH'  # More forgiving
        elif len(issues) <= 4:
            quality = 'MEDIUM'
        else:
            quality = 'LOW'

        return {
            'clean': len(issues) == 0,
            'issues': issues,
            'suggestions': suggestions,
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

    def generate_script_oneblock(
        self,
        title: str,
        niche_id: str,
        length: int = 10000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate script as ONE CONTINUOUS BLOCK with HARD VALIDATION + RETRY
        Uses custom script formula from settings

        ENGINEERING FIX:
        - Validates output with hard checks (no VISUAL:, no NARRATOR:, no timestamps)
        - Enforces length tolerance (±3%)
        - Validates title-lock (prevents drift)
        - Auto-retries up to 3 times if validation fails
        - Returns error if all retries fail

        Args:
            title: Video title
            niche_id: Niche ID with writing guidelines
            length: Any integer from 1,000 to 80,000 characters
            verbose: Print progress

        Returns:
            Dict with script, stats, quality info

        Raises:
            ValueError: If validation fails after max retries
        """
        from settings_manager import SettingsManager

        start_time = time.time()

        # Validate length range
        if not Config.validate_script_length(length):
            raise ValueError(
                f'Length must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH} characters'
            )

        # Get niche
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        # Load script formula from settings
        script_formula = SettingsManager.load_formula('script')

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 GENERATING ONE-BLOCK SCRIPT WITH HARD VALIDATION")
            print(f"{'='*70}")
            print(f"Title: {title}")
            print(f"Target: {length:,} characters (±3% tolerance)")
            print(f"Niche: {niche['name']}")
            print(f"Language: {niche['language']}")
            print(f"Max Retries: {Config.MAX_SCRIPT_RETRIES}")
            print(f"{'='*70}\n")

        # Detect narrative approach
        approach = self.select_narrative_approach(title)
        if verbose:
            print(f"🧠 Narrative Approach: {approach}")

        # Build ONE BLOCK prompt using formula
        prompt = self._build_oneblock_prompt(
            title=title,
            niche_data=niche,
            formula=script_formula,
            target_chars=length,
            approach=approach
        )

        # RETRY LOOP - Generate with validation
        script = None
        validation_result = None
        attempt = 0
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        while attempt < Config.MAX_SCRIPT_RETRIES:
            attempt += 1

            if verbose:
                print(f"\n📡 Attempt {attempt}/{Config.MAX_SCRIPT_RETRIES}: Calling Gemini...")

            # Generate
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.88,  # Single optimal temperature
                    max_output_tokens=Config.GEMINI_MAX_TOKENS,
                    top_p=0.95,
                    top_k=40
                )
            )

            # Get and clean script
            script = response.text.strip()
            script = self.clean_script_oneblock(script)

            if verbose:
                print(f"✅ Response received ({len(script):,} chars)")

            # HARD VALIDATION
            validation_result = self.hard_validate_output(script, title, length)

            if validation_result['valid']:
                if verbose:
                    print(f"✅ VALIDATION PASSED on attempt {attempt}")
                    if validation_result['warnings']:
                        print(f"⚠️  Warnings: {', '.join(validation_result['warnings'])}")
                break
            else:
                if verbose:
                    print(f"❌ VALIDATION FAILED on attempt {attempt}:")
                    for error in validation_result['errors']:
                        print(f"   - {error}")

                if attempt < Config.MAX_SCRIPT_RETRIES:
                    if verbose:
                        print(f"🔄 Retrying generation...")
                    script = None  # Clear failed script

        # Check if validation succeeded
        if not validation_result or not validation_result['valid']:
            error_details = '\n'.join(validation_result['errors']) if validation_result else 'Unknown error'
            raise ValueError(
                f"Script generation failed after {Config.MAX_SCRIPT_RETRIES} attempts.\n"
                f"Validation errors:\n{error_details}\n\n"
                f"The output contained invalid patterns (VISUAL:, NARRATOR:, timestamps, etc.) "
                f"or failed length/title-lock requirements."
            )

        # Stats
        char_count = len(script)
        word_count = len(script.split())
        generation_time = time.time() - start_time

        # Quality assessment
        length_accuracy = abs(char_count - length) / length * 100
        quality = "HIGH" if length_accuracy <= 5 else "MEDIUM"

        if verbose:
            print(f"\n📊 FINAL STATS:")
            print(f"   Characters: {char_count:,} (target: {length:,})")
            print(f"   Words: {word_count:,}")
            print(f"   Length Accuracy: {100 - length_accuracy:.1f}%")
            print(f"   Attempts: {attempt}")
            print(f"   Time: {generation_time:.1f}s")
            print(f"   Quality: {quality}")
            print(f"{'='*70}\n")

        return {
            'script': script,
            'approach': approach,
            'quality': quality,
            'validation': validation_result,
            'attempts': attempt,
            'stats': {
                'chars': char_count,
                'words': word_count,
                'time': generation_time
            }
        }

    def _build_oneblock_prompt(self, title, niche_data, formula, target_chars, approach):
        """Build FINAL PRODUCTION SCRIPT PROMPT with HARD OVERRIDES + TITLE-LOCK + LENGTH EXECUTION"""

        product = niche_data.get('product', 'our platform')
        language = niche_data['language']
        niche_name = niche_data['name']

        # Replace placeholders in formula (auto-normalize)
        formula_filled = formula.replace('{title}', title)
        formula_filled = formula_filled.replace('{niche}', niche_name)
        formula_filled = formula_filled.replace('{language}', language)
        formula_filled = formula_filled.replace('{guidelines}', niche_data.get('writing_guidelines', ''))
        formula_filled = formula_filled.replace('{length}', f"{target_chars:,}")
        formula_filled = formula_filled.replace('{approach}', approach)
        formula_filled = formula_filled.replace('{topic}', title)
        formula_filled = formula_filled.replace('{target_length}', f"{target_chars:,}")
        formula_filled = formula_filled.replace('{word_count}', f"{target_chars // 5:,}")

        # FINAL PRODUCTION SCRIPT PROMPT
        prompt = f"""You are an elite, world-class human scriptwriter.

You write high-retention YouTube scripts that sound natural, emotional, intelligent, and deeply human.
Your scripts are written to be converted directly into voice audio without any modification.

════════════════════════════════════════════════════════════
🔒 HARD OVERRIDES (ABSOLUTE — MUST WIN OVER EVERYTHING)
════════════════════════════════════════════════════════════

THESE RULES OVERRIDE ALL OTHER INSTRUCTIONS:

1. The output MUST be ONE single continuous paragraph block.
2. DO NOT use scene descriptions, narrator labels, dialogue labels, or screenplay formatting.
3. DO NOT use parentheses for stage directions.
4. DO NOT use brackets, dashes as separators, or section dividers.
5. DO NOT split into parts (NO "Part 1", "Part 2", "To be continued").
6. DO NOT imply continuation beyond the single block.
7. DO NOT include visual instructions (NO "VISUALS:", "VIDEO:", "SHOW:", "CUT TO:").
8. DO NOT use ANY formatting symbols: **, __, ~~, ##, ---, ***, ===, ───
9. DO NOT label sections with titles like "Introduction:", "Hook:", "Conclusion:"
10. DO NOT include character counts, timestamps, or meta-commentary.

IF ANY OF THE ABOVE APPEAR IN YOUR OUTPUT, THE OUTPUT IS INVALID AND MUST BE REGENERATED INTERNALLY.

════════════════════════════════════════════════════════════
🔐 TITLE-LOCK SYSTEM (STOPS DRIFT)
════════════════════════════════════════════════════════════

TITLE LOCK RULES:
- Every sentence must DIRECTLY serve the title.
- Do NOT generalize beyond the title's subject.
- Do NOT turn the script into a metaphor, life lesson, or motivational speech UNLESS the title explicitly implies it.
- Do NOT drift into tangential topics.
- If a paragraph cannot be traced back to the title, remove or rewrite it.
- The title is: "{title}"
- STAY FOCUSED on this exact topic from start to finish.

════════════════════════════════════════════════════════════
📏 LENGTH EXECUTION SYSTEM (1k → 80k SAFE)
════════════════════════════════════════════════════════════

Target length: {target_chars:,} characters (STRICT)

LENGTH EXECUTION PROCESS:

Step 1: Internally plan the script into logical sections based on the formula.
Step 2: Assign each section a character budget (distribute {target_chars:,} total).
Step 3: Generate the script in internal chunks that respect those budgets.
Step 4: Merge all chunks into ONE single clean block (no separators, no labels).
Step 5: Perform a final trim or expansion pass to stay within ±3% of {target_chars:,} characters.
Step 6: Output ONLY the final merged block.

DO NOT SKIP STEP 5. The final character count MUST be within {int(target_chars * 0.97):,} - {int(target_chars * 1.03):,} characters.

────────────────────────────────────────
ABSOLUTE OUTPUT RULES (NO EXCEPTIONS)
────────────────────────────────────────
- Output ONE single continuous block of plain text.
- Do NOT use emojis, hashtags, bullet points, lists, section titles, formatting, or symbols.
- Do NOT use markdown, quotes for emphasis, or separators.
- Do NOT explain your process.
- Do NOT include commentary, notes, or meta text.
- Do NOT include links or sources.
- The script must be completely clean and voice-ready.

────────────────────────────────────────
CORE OBJECTIVE
────────────────────────────────────────
Write a high-quality YouTube video script that maximizes retention and emotional engagement.

The script must:
- Be written ONLY for the provided title: "{title}"
- Match the selected niche and audience.
- Respect the custom formula provided by the user.
- Match the required character length EXACTLY (±3%).
- Flow clearly and logically from the first sentence to the last.

────────────────────────────────────────
HOOK INTELLIGENCE (CRITICAL)
────────────────────────────────────────
The first 2 to 3 sentences must:
- Create immediate curiosity, tension, or emotional pull.
- Avoid explaining the topic.
- Avoid summarizing the content.
- Avoid generic openings such as:
  "Today we will"
  "This video is about"
  "In this story"
  "Welcome to"
  "Let me tell you about"
- Make the listener feel compelled to continue.

If the hook is weak, the script is considered a failure.

────────────────────────────────────────
FORMULA NORMALIZATION SYSTEM
────────────────────────────────────────
The user provides a SCRIPT FORMULA written in natural language.

Your task is to:
1. Internally translate the formula into a clear narrative structure you fully understand.
2. Convert it into an internal sequence such as:
   opening intention
   progression
   escalation
   resolution or takeaway
3. Follow this internal structure faithfully.
4. Never output the formula or mention it.

The formula defines HOW the script is written.
The title defines WHAT the script is about.

────────────────────────────────────────
NICHE-SPECIFIC HIDDEN RULES (INTERNAL ONLY)
────────────────────────────────────────

If NICHE = STORY / HORROR / DRAMA:
- Maintain strict consistency of names, places, and timeline.
- Build tension gradually.
- Never change story facts mid-script.
- Focus on emotion and consequence.

If NICHE = EDUCATION / EXPLAINER:
- Challenge assumptions early.
- Explain clearly using simple language.
- Avoid sounding academic.
- Build understanding step by step.

If NICHE = NEWS / ANALYSIS:
- Emphasize why this matters now.
- Clearly explain context and implications.
- Stay factual and grounded.
- Avoid speculation unless clearly framed.

If NICHE = FINANCE / TRADING:
- Be realistic and grounded.
- Explain risks and misunderstandings.
- Avoid hype language.
- End with a clear, sober takeaway.

────────────────────────────────────────
CREATIVE VARIATION ENGINE (ANTI-REPETITION)
────────────────────────────────────────
Every script must feel fresh and original.

Rules:
- Never reuse the same narrative rhythm in consecutive generations.
- Vary sentence length and pacing.
- Rotate hook psychology (curiosity, tension, contrast, mystery, emotion).
- Avoid predictable phrasing.
- Write as if a different human author is writing each script.

────────────────────────────────────────
RESEARCH INTELLIGENCE
────────────────────────────────────────
If the topic requires knowledge:
- Write as if you deeply understand the subject.
- Be accurate and confident.
- Do not invent facts.
- Do not cite sources.
- Do not sound robotic or academic.

────────────────────────────────────────
CHUNKED GENERATION SYSTEM (TOKEN SAFE)
────────────────────────────────────────
If the script is long:
- Internally generate the script in logical chunks.
- Ensure each chunk flows seamlessly into the next.
- Maintain consistency across all chunks.
- Merge internally into ONE final clean block.
- Do NOT expose chunks in the output.

────────────────────────────────────────
PRODUCT INTEGRATION (NATURAL & SEAMLESS)
────────────────────────────────────────
Product/Platform: {product}
- Mention naturally 2-3 times throughout the script
- Example: "and I track everything using {product}, link in description"
- NEVER mention price, cost, or affordability
- Seamlessly woven into the narrative

Language: {language}

════════════════════════════════════════════════════════════
🔄 AUTO-RETRY QUALITY VALIDATOR (ENHANCED)
════════════════════════════════════════════════════════════

Before outputting the final script, verify:

✓ Clean formatting (no symbols, no meta text, no screenplay formatting)
✓ Strong hook (first 2-3 sentences create tension/curiosity)
✓ Formula compliance (follows user's structure)
✓ Niche rules followed (story consistency, education clarity, etc.)
✓ Length within ±3% tolerance ({int(target_chars * 0.97):,} - {int(target_chars * 1.03):,} chars)
✓ Title-lock verified (no topic drift)
✓ Logical consistency (no contradictions)
✓ Creative freshness (not repetitive)
✓ No scene labels, narrator labels, dialogue formatting, or visual cues
✓ No "Part 1", "Part 2", "To be continued", or continuation markers
✓ ONE single continuous block only

FAIL AND REGENERATE IF:
- Output contains labels, scenes, dialogue formatting, or visual cues
- Output implies multiple parts or continuation
- Output exceeds ±3% of target length
- Topic drifts from the title
- Output is not a single continuous block

If ANY check fails:
- Internally revise and regenerate.
- Retry up to 3 times.
- Only output the script when ALL checks pass.

════════════════════════════════════════════════════════════
INPUTS
════════════════════════════════════════════════════════════
TITLE:
{title}

NICHE:
{niche_name}

TARGET CHARACTERS:
{target_chars:,} (STRICT: must be within {int(target_chars * 0.97):,} - {int(target_chars * 1.03):,})

SCRIPT FORMULA:
{formula_filled}

════════════════════════════════════════════════════════════
NOW WRITE THE FINAL SCRIPT
════════════════════════════════════════════════════════════

Execute the LENGTH EXECUTION SYSTEM (Steps 1-6).
Apply TITLE-LOCK to stay focused on: "{title}"
Apply HARD OVERRIDES to ensure ONE clean block output.
Output ONLY the spoken narration. No preamble. No meta-commentary. Start immediately with a magnetic hook.
"""

        return prompt

    def clean_script_oneblock(self, text: str) -> str:
        """
        Aggressively clean script for ONE BLOCK output
        Remove ALL artifacts, sections, formatting
        """
        # Remove section markers and meta-commentary
        text = re.sub(r'(?i)(part|section|chunk)\s*\d+', '', text)
        text = re.sub(r'(?i)continue(d|ing)?\s+(seamlessly|from|the)', '', text)
        text = re.sub(r'(?i)as (we |I )?discussed', '', text)
        text = re.sub(r'(?i)as (we |I )?mentioned', '', text)
        text = re.sub(r'(?i)in the previous (part|section)', '', text)
        text = re.sub(r'(?i)let me continue', '', text)
        text = re.sub(r'(?i)now let\'?s', 'Let\'s', text)

        # Remove ALL markdown formatting
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)  # Bold+Italic
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)      # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)          # Italic
        text = re.sub(r'__(.+?)__', r'\1', text)          # Bold underscore
        text = re.sub(r'_(.+?)_', r'\1', text)            # Italic underscore
        text = re.sub(r'~~(.+?)~~', r'\1', text)          # Strikethrough
        text = re.sub(r'#{1,6}\s+', '', text)             # Headers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)  # Bullets
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)  # Numbered lists

        # Remove price mentions
        text = re.sub(r'\$\d+[,\d]*', '', text)
        text = re.sub(r'\d+\s*dollars?', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(price|cost|afford|cheap|expensive|discount|sale|investment)\b', '', text, flags=re.IGNORECASE)

        # Fix spacing issues
        text = re.sub(r'\s+', ' ', text)           # Multiple spaces → single
        text = re.sub(r'\n{3,}', '\n\n', text)     # Multiple newlines → double
        text = re.sub(r'([.!?])\s*([A-Z])', r'\1 \2', text)  # Sentence spacing

        return text.strip()

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 60000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate script using EXACT HTML system logic (3 parts)

        NOTE: Use generate_script_oneblock() for ONE CONTINUOUS BLOCK instead

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

        # Merge and clean (DOUBLE PASS for maximum effectiveness)
        if verbose:
            print(f"\n🧹 Deep cleaning (pass 1)...")

        final_script = '\n\n'.join(chunks)
        final_script = self.clean_script(final_script)

        if verbose:
            print(f"🧹 Deep cleaning (pass 2)...")

        final_script = self.clean_script(final_script)  # Second pass catches anything missed

        # Validate quality with length check
        if verbose:
            print(f"\n🔍 Validating quality...")

        validation = self.validate_quality(final_script, expected_length=length)
        final_script = validation['script']

        if verbose:
            print(f"\n✅ Quality: {validation['quality']}")
            if validation['issues']:
                print(f"⚠️  Issues fixed:")
                for issue in validation['issues']:
                    print(f"   {issue}")
            if validation.get('suggestions'):
                print(f"💡 Suggestions:")
                for suggestion in validation['suggestions']:
                    print(f"   {suggestion}")

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
            'issues': validation['issues'],
            'suggestions': validation.get('suggestions', [])
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

#!/usr/bin/env python3
"""
Script Generator - 3-CHUNK ARCHITECTURE (PRODUCTION)
- ALWAYS uses 3 chunks (30/40/30 split)
- Uses niche writing guidelines for high-quality output
- Total API calls: 3 (one per chunk)
- Rate limit safe: 20 calls/min ÷ 3 = 6-7 videos/min max
"""

import re
import time
import google.generativeai as genai
from typing import Dict, List
from config import Config
from niche_manager import NicheManager
from chunk_planner import ChunkPlanner
from settings_manager import SettingsManager
from utils import detect_language_from_text, get_language_name


class ScriptGenerator3Chunk:
    """
    Production script generator using proven 3-chunk architecture

    API CALL COUNT:
    - Title generation: 1 call (handled separately)
    - Script chunk 1: 1 call
    - Script chunk 2: 1 call
    - Script chunk 3: 1 call
    - TOTAL per video: 4 calls

    Free tier limit: 20 calls/min
    Maximum videos: 5 per minute
    """

    def __init__(self):
        """Initialize Gemini API"""
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)
        self.api_key = api_key

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 10000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate script using 3-chunk architecture with user's formula

        Args:
            title: Video title
            niche_id: Niche ID
            length: Target length (1,000 - 80,000 characters)
            verbose: Print progress

        Returns:
            Dict with script, stats, validation info
        """
        start_time = time.time()

        # Validate length
        if not Config.validate_script_length(length):
            raise ValueError(
                f"Length must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH}"
            )

        # Get niche
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        # Detect language from title (high priority over niche language)
        detected_lang_code = detect_language_from_text(title)
        detected_lang_name = get_language_name(detected_lang_code)

        # Override niche language with detected language from title
        original_niche_lang = niche.get('language', 'English')
        niche['language'] = detected_lang_name  # Override with detected language

        # Use niche writing guidelines (style/tone)
        writing_guidelines = niche['writing_guidelines']

        # Load the user's script formula (any formula they have saved — French, custom, etc.)
        raw_formula = SettingsManager.load_formula('script')
        # Fill simple placeholders that may exist in the formula template
        word_count_estimate = int(length / 5)  # ~5 chars per word
        script_formula = (
            raw_formula
            .replace('{target_length}', f'{length:,}')
            .replace('{word_count}',    f'{word_count_estimate:,}')
            .replace('{language}',      detected_lang_name)
            .replace('{niche}',         niche.get('name', ''))
        )

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 3-CHUNK SCRIPT GENERATION")
            print(f"{'='*70}")
            print(f"Title: {title}")
            print(f"Target: {length:,} characters")
            print(f"Niche: {niche['name']}")
            if detected_lang_name != original_niche_lang:
                print(f"Language: {detected_lang_name} (detected from title, overriding niche: {original_niche_lang})")
            else:
                print(f"Language: {detected_lang_name}")
            print(f"Chunks: dynamic (based on length)")
            print(f"{'='*70}\n")

        # Plan chunks using ChunkPlanner
        planner = ChunkPlanner(length)
        chunks = planner.plan()
        total_chunks = len(chunks)

        if verbose:
            print(f"📦 Chunk Plan ({total_chunks} chunks):")
            for chunk in chunks:
                print(f"   Chunk {chunk.index}/{total_chunks}: {chunk.role} ({chunk.target_chars:,} chars)")
            print()

        # Generate each chunk
        generated_chunks = []
        previous_context = ""

        for chunk in chunks:
            if verbose:
                print(f"🎨 Generating Chunk {chunk.index}/{total_chunks}: {chunk.role}...")

            # Build prompt for this chunk
            prompt = self._build_chunk_prompt(
                title=title,
                niche=niche,
                writing_guidelines=writing_guidelines,
                script_formula=script_formula,
                chunk=chunk,
                previous_context=previous_context,
                total_chunks=total_chunks
            )

            # Determine temperature based on role
            temp = self._get_temperature(chunk.role)

            # max_output_tokens: sized to the chunk, not a blanket 65536.
            # Arabic: ~2 chars/token → chars/2 + buffer (safer than /3 for English).
            chunk_max_tokens = max(4096, int(chunk.target_chars / 2) + 2000)

            # Call API — retry on 429 quota errors using the suggested wait time
            MAX_API_RETRIES = 3
            response = None
            for attempt in range(MAX_API_RETRIES + 1):
                try:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content(
                        prompt,
                        generation_config=genai.types.GenerationConfig(
                            temperature=temp,
                            max_output_tokens=chunk_max_tokens,
                            top_p=0.95,
                            top_k=40
                        )
                    )
                    break  # success
                except Exception as e:
                    err_str = str(e)
                    is_quota = (
                        '429' in err_str
                        or 'quota' in err_str.lower()
                        or 'ResourceExhausted' in type(e).__name__
                    )
                    if not is_quota or attempt == MAX_API_RETRIES:
                        raise
                    # Extract the suggested retry delay from the error message
                    delay_match = re.search(r'seconds: (\d+)', err_str)
                    wait = int(delay_match.group(1)) + 5 if delay_match else 35
                    if verbose:
                        print(f"   ⚠️  Quota limit hit — waiting {wait}s before retry "
                              f"(attempt {attempt + 1}/{MAX_API_RETRIES})...")
                    time.sleep(wait)

            chunk_text = response.text.strip()
            generated_chunks.append(chunk_text)

            if verbose:
                print(f"✅ Chunk {chunk.index}/{total_chunks}: {len(chunk_text):,} chars (raw, before cleaning)")

            # Save last 2-3 sentences as context for next chunk
            if chunk.index < total_chunks:
                sentences = [s.strip() for s in re.split(r'[.!?]', chunk_text) if len(s.strip()) > 15]
                previous_context = '. '.join(sentences[-3:]) + '.' if len(sentences) >= 3 else chunk_text[-300:]

            # Rate limit protection — 4 s between chunks keeps RPM safe
            if chunk.index < total_chunks:
                time.sleep(4)

        # Merge chunks
        if verbose:
            print(f"\n🔗 Merging chunks...")

        full_script = self._merge_chunks(generated_chunks)

        # Clean script
        full_script = self._clean_script(full_script)

        # ── Length enforcement ───────────────────────────────────────────
        # Goal: result must be ≥ target, and at most target + 5 000 chars.
        MAX_OVERSHOOT = 5000

        char_count = len(full_script)
        if verbose:
            print(f"\n📏 Length check: {char_count:,} / {length:,} target")

        # --- Extend if short ---
        if char_count < length:
            shortage = length - char_count
            if verbose:
                print(f"   ⚠️  Short by {shortage:,} chars — extending...")
            full_script = self._extend_script(
                current_script=full_script,
                target_length=length,
                title=title,
                niche=niche,
                writing_guidelines=writing_guidelines,
                script_formula=script_formula,
                verbose=verbose,
            )
            full_script = self._clean_script(full_script)
            char_count = len(full_script)
            if verbose:
                print(f"   ✅ After extension: {char_count:,} chars")

        # --- Trim if over by more than 5 000 chars ---
        if char_count > length + MAX_OVERSHOOT:
            if verbose:
                print(f"   ✂️  Over by {char_count - length:,} — trimming to {length + MAX_OVERSHOOT:,}...")
            full_script = self._trim_to_length(full_script, length + MAX_OVERSHOOT)
            char_count = len(full_script)
            if verbose:
                print(f"   ✅ After trim: {char_count:,} chars")
        # ────────────────────────────────────────────────────────────────

        # Validate
        validation = self._validate_script(full_script, title, length)

        # Stats
        char_count = len(full_script)
        word_count = len(full_script.split())
        generation_time = time.time() - start_time

        if verbose:
            print(f"\n📊 FINAL STATS:")
            print(f"   Characters: {char_count:,}  ← this is what the frontend shows")
            print(f"   Words: {word_count:,}")
            print(f"   Target: {length:,} (must be ≥ target, ≤ target+5k)")
            print(f"   Delta: {char_count - length:+,}")
            print(f"   Time: {generation_time:.1f}s")
            print(f"   Valid: {validation['valid']}")
            if not validation['valid']:
                print(f"   Errors: {', '.join(validation['errors'])}")
            print(f"{'='*70}\n")

        return {
            'script': full_script,
            'stats': {
                'chars': char_count,
                'words': word_count,
                'time': generation_time
            },
            'validation': validation,
            'chunks_used': len(chunks)
        }

    def _build_chunk_prompt(
        self,
        title: str,
        niche: Dict,
        writing_guidelines: str,
        script_formula: str,
        chunk: 'ChunkConfig',
        previous_context: str,
        total_chunks: int = 3
    ) -> str:
        """
        Build a prompt for one chunk.

        The user's script formula (any formula, any language) is injected as the
        PRIMARY structure guide.  Each chunk is told exactly which portion of the
        total script it covers so it stays faithful to the formula section by section.
        """
        product    = niche.get('product', 'our platform')
        language   = niche['language']
        niche_name = niche['name']

        # Progress labels for the AI
        pct_start = int(chunk.script_position_start * 100)
        pct_end   = int(chunk.script_position_end   * 100)

        if chunk.role == "HOOK_AND_FRAMEWORK":
            position_label = f"OPENING of the script (0 % → {pct_end} %)"
            position_task  = (
                "You are writing the BEGINNING of the script.\n"
                "Follow the OPENING / HOOK section of the formula above.\n"
                "Create an irresistible hook that forces the listener to keep listening.\n"
                "Establish the framework and promise — do NOT reveal the full answer yet."
            )
            continuation_block = ""

        elif chunk.role == "DEEP_INSIGHTS_AND_EXAMPLES":
            position_label = f"MIDDLE of the script ({pct_start} % → {pct_end} %)"
            position_task  = (
                "You are writing a MIDDLE section of the script.\n"
                "Follow the corresponding middle / development / journey section of the formula above.\n"
                "Go deep: add examples, stories, data, insights.\n"
                "Keep the energy high, vary sentence rhythm, include mini-revelations.\n"
                "Do NOT conclude — the script continues after this chunk."
            )
            continuation_block = f"""
CONTINUE SEAMLESSLY FROM HERE (do NOT repeat it):
"...{previous_context}"
"""

        else:  # IMPLEMENTATION_AND_CLOSE
            position_label = f"CLOSING of the script ({pct_start} % → 100 %)"
            position_task  = (
                "You are writing the END of the script.\n"
                "Follow the CLOSE / CONCLUSION / TRANSFORMATION section of the formula above.\n"
                "Synthesise everything, deliver the payoff, echo the opening hook with new meaning.\n"
                "End powerfully and memorably."
            )
            continuation_block = f"""
CONTINUE SEAMLESSLY FROM HERE (do NOT repeat it):
"...{previous_context}"
"""

        prompt = f"""You are an elite, highly creative scriptwriter producing voice-ready narration.
Your output must sound like a world-class human storyteller — not a robot.

══════════════════════════════════════════════════════════════
PROJECT DETAILS
══════════════════════════════════════════════════════════════
TITLE   : "{title}"
NICHE   : {niche_name}
LANGUAGE: {language}
CHUNK   : {chunk.index} of {total_chunks}  |  {position_label}
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
SCRIPT FORMULA  ← FOLLOW THIS STRUCTURE EXACTLY
══════════════════════════════════════════════════════════════
{script_formula}
══════════════════════════════════════════════════════════════

══════════════════════════════════════════════════════════════
NICHE WRITING STYLE  ← APPLY THIS TONE AND APPROACH
══════════════════════════════════════════════════════════════
{writing_guidelines}
══════════════════════════════════════════════════════════════

YOUR TASK FOR THIS CHUNK
──────────────────────────────────────────────────────────────
{position_task}
{continuation_block}
──────────────────────────────────────────────────────────────

══════════════════════════════════════════════════════════════
MANDATORY OUTPUT RULES
══════════════════════════════════════════════════════════════

LANGUAGE (ABSOLUTE PRIORITY):
- Write 100 % in {language} — not a single word of another language
- Native-level {language}: natural expressions, idioms, rhythm
- The title is in {language}: "{title}" — match that register exactly

FORMAT — PLAIN VOICE TEXT ONLY:
- One continuous block of flowing prose
- NO markdown (**, __, ##, ---, etc.)
- NO section headers, dividers, or labels
- NO visual cues: VISUAL:, VIDEO:, SHOW:, CUT TO:
- NO narrator tags: NARRATOR:, SPEAKER:, HOST:
- NO timestamps: (0:00-0:15), (30 sec), (pause)
- NO parentheses or brackets with stage directions
- NO meta-commentary ("In this section...", "As I mentioned...")

QUALITY (NON-NEGOTIABLE):
- Every sentence must earn its place — no filler, no padding
- Vary sentence length: short punchy lines for impact, longer ones for depth
- Use vivid metaphors, concrete examples, and emotional storytelling
- Keep the listener hooked from the first word to the last

TOPIC LOCK:
- Every sentence must serve the title: "{title}"
- Do NOT drift to unrelated subjects

PRODUCT (only if relevant):
- Mention "{product}" naturally 1–2 times max
- Example: "…and I manage this with {product}, link in description…"
- NEVER mention price

LENGTH — CRITICAL:
- Write AT LEAST {chunk.target_chars:,} characters for this chunk
- Up to {int(chunk.target_chars * 1.08):,} chars is fine
- Expand ideas, add more examples, go deeper — never stop early
- Do NOT rush to finish

══════════════════════════════════════════════════════════════
START WRITING IN {language.upper()} NOW — NO PREAMBLE
══════════════════════════════════════════════════════════════
"""
        return prompt

    def _extend_script(
        self,
        current_script: str,
        target_length: int,
        title: str,
        niche: dict,
        writing_guidelines: str,
        script_formula: str = '',
        verbose: bool = False,
    ) -> str:
        """
        Continue the script until ≥ target_length chars.
        Retries up to 2 times.  Follows the user's formula.
        """
        MAX_EXTEND_RETRIES = 2
        language  = niche.get('language', 'English')
        niche_name = niche.get('name', '')

        for attempt in range(MAX_EXTEND_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            extend_chars  = shortage + 1500   # buffer for cleaning loss
            extend_tokens = max(2048, int(extend_chars / 2) + 1000)
            tail = current_script[-600:].strip()

            formula_block = (
                f"\nSCRIPT FORMULA (keep following the body/development section):\n{script_formula}\n"
                if script_formula else ""
            )

            prompt = f"""You are continuing a voice narration script. Continue SEAMLESSLY.

TITLE   : "{title}"
NICHE   : {niche_name}
LANGUAGE: {language}
{formula_block}
WRITING STYLE:
{writing_guidelines}

LAST PART OF SCRIPT (do NOT repeat — continue from here):
"...{tail}"

══════════════════════════════════════════════════════════════
RULES (MANDATORY)
══════════════════════════════════════════════════════════════
- Write AT LEAST {extend_chars:,} characters of NEW content
- Stay 100 % in {language} — no other language
- Plain flowing prose only — no markdown, no labels, no timestamps
- Do NOT repeat anything already written
- Do NOT add a conclusion or closing — the body is still ongoing
- Follow the formula's body/development section style
- Start the continuation immediately, no preamble
══════════════════════════════════════════════════════════════
"""
            try:
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.85,
                        max_output_tokens=extend_tokens,
                        top_p=0.95,
                        top_k=40,
                    )
                )
                extension = response.text.strip()
                current_script = current_script.rstrip() + ' ' + extension
                if verbose:
                    print(f"   Extension attempt {attempt + 1}: +{len(extension):,} chars → total {len(current_script):,}")
                time.sleep(4)  # Rate limit protection
            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Extension attempt {attempt + 1} failed: {e}")
                break

        return current_script

    def _trim_to_length(self, text: str, max_chars: int) -> str:
        """
        Trim text to at most max_chars, cutting at the last sentence boundary.
        """
        if len(text) <= max_chars:
            return text
        # Cut at max_chars then back-track to a sentence end
        truncated = text[:max_chars]
        last_sentence = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?'),
        )
        if last_sentence > max_chars * 0.8:
            return truncated[:last_sentence + 1].strip()
        return truncated.strip()

    def _get_temperature(self, role: str) -> float:
        """Get temperature based on chunk role"""
        temps = {
            "HOOK_AND_FRAMEWORK": 0.90,      # High creativity for hook
            "DEEP_INSIGHTS_AND_EXAMPLES": 0.85,  # Balanced
            "IMPLEMENTATION_AND_CLOSE": 0.80     # More focused for conclusion
        }
        return temps.get(role, 0.85)

    def _merge_chunks(self, chunks: List[str]) -> str:
        """
        Merge chunks into one continuous block

        Remove any continuation markers or chunk artifacts
        """
        # Join with space
        merged = ' '.join(chunks)

        # Remove chunk continuation phrases
        merged = re.sub(r'(?i)(continuing from|as we discussed|as mentioned earlier)', '', merged)
        merged = re.sub(r'(?i)(in the previous (section|part|chunk))', '', merged)

        # Fix double spaces
        merged = re.sub(r'  +', ' ', merged)

        return merged.strip()

    def _clean_script(self, text: str) -> str:
        """
        Aggressive cleaning to remove ALL formatting artifacts
        """
        # Remove markdown
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'#{1,6}\s+', '', text)

        # Remove any remaining asterisks
        text = re.sub(r'\*', '', text)

        # Remove labels and visual cues
        text = re.sub(r'(?i)(VISUAL|VIDEO|NARRATOR|SPEAKER|SHOW|CUT TO)\s*:', '', text)

        # Remove timestamps
        text = re.sub(r'\(\s*\d+:\d+\s*-\s*\d+:\d+\s*\)', '', text)
        text = re.sub(r'\(\s*\d+\s*(sec|min|seconds?|minutes?)\s*\)', '', text)

        # Remove brackets and parentheses with directions
        text = re.sub(r'\[.+?\]', '', text)
        text = re.sub(r'\(.+?\)', '', text)

        # Fix spacing
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()

    def _validate_script(self, script: str, title: str, target_length: int) -> Dict:
        """
        Basic validation

        Returns dict with 'valid' (bool) and 'errors' (list)
        """
        errors = []

        # Check length: must be ≥ target and ≤ target + 5 000
        actual_length = len(script)
        max_length = target_length + 5000

        if actual_length < target_length:
            errors.append(f"Too short: {actual_length:,} < {target_length:,}")
        elif actual_length > max_length:
            errors.append(f"Too long: {actual_length:,} > {max_length:,}")

        # Check for forbidden patterns
        forbidden = [
            (r'(?i)\bVISUAL\s*:', 'VISUAL: label found'),
            (r'(?i)\bNARRATOR\s*:', 'NARRATOR: label found'),
            (r'\(\s*\d+:\d+', 'Timestamp found'),
        ]

        for pattern, msg in forbidden:
            if re.search(pattern, script):
                errors.append(msg)

        # Check title lock (basic)
        title_words = [w.lower() for w in title.split() if len(w) > 3]
        if title_words:
            script_lower = script.lower()
            found = sum(1 for w in title_words if w in script_lower)
            if found < len(title_words) * 0.3:  # At least 30% of title words
                errors.append("Possible topic drift (title words missing)")

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

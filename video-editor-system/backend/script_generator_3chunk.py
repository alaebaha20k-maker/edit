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

        # The niche writing_guidelines IS the user's content formula —
        # it defines both the structure and the style for every script.
        writing_guidelines = niche['writing_guidelines']

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

        # Build system instruction once — formula as model identity (highest priority)
        system_instruction = self._build_system_instruction(writing_guidelines, niche['language'])

        if verbose:
            print(f"📋 System instruction: {len(system_instruction):,} chars (formula as model identity)")

        # Generate each chunk
        generated_chunks = []
        previous_context = ""

        for chunk in chunks:
            if verbose:
                print(f"🎨 Generating Chunk {chunk.index}/{total_chunks}: {chunk.role}...")

            # Build user-turn prompt for this chunk (formula already in system instruction)
            prompt = self._build_chunk_prompt(
                title=title,
                niche=niche,
                writing_guidelines=writing_guidelines,
                chunk=chunk,
                previous_context=previous_context,
                total_chunks=total_chunks
            )

            # Determine temperature based on role
            temp = self._get_temperature(chunk.role)

            # Dynamic token budget per chunk — avoids reserving 65536 tokens
            # when the chunk only needs a fraction of that.
            # chars/3 ≈ tokens for French/Arabic; add 20% buffer + 2000 safety margin
            chunk_tokens = min(65536, max(int(chunk.target_chars / 3 * 1.20) + 2000, 4000))

            # Call API — retry on 429 quota errors using the suggested wait time.
            # Also retry immediately if the chunk output is < 50 % of target
            # (happens when the model truncates early).
            MAX_API_RETRIES = 3
            MAX_SHORT_RETRIES = 2
            response = None
            chunk_text = ""

            for short_attempt in range(MAX_SHORT_RETRIES + 1):
                for attempt in range(MAX_API_RETRIES + 1):
                    try:
                        # Create model with formula as system instruction —
                        # this gives the formula the highest possible priority.
                        model = genai.GenerativeModel(
                            'gemini-2.5-flash',
                            system_instruction=system_instruction
                        )
                        gen_cfg = {
                            "temperature": temp,
                            "max_output_tokens": chunk_tokens,
                            "top_p": 0.95,
                            "top_k": 40,
                        }
                        response = model.generate_content(prompt, generation_config=gen_cfg)
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
                        delay_match = re.search(r'seconds: (\d+)', err_str)
                        wait = int(delay_match.group(1)) + 5 if delay_match else 35
                        if verbose:
                            print(f"   ⚠️  Quota limit hit — waiting {wait}s before retry "
                                  f"(attempt {attempt + 1}/{MAX_API_RETRIES})...")
                        time.sleep(wait)

                chunk_text = response.text.strip()

                # Retry if output is suspiciously short (< 50 % of target)
                min_acceptable = int(chunk.target_chars * 0.50)
                if len(chunk_text) >= min_acceptable or short_attempt == MAX_SHORT_RETRIES:
                    break
                if verbose:
                    print(f"   ⚠️  Output too short ({len(chunk_text):,} < {min_acceptable:,}) "
                          f"— retrying chunk (attempt {short_attempt + 1}/{MAX_SHORT_RETRIES})...")
                time.sleep(4)

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

    def _build_system_instruction(self, writing_guidelines: str, language: str) -> str:
        """
        Build the Gemini system instruction.

        The niche Content Formula is placed here — in the system instruction
        slot — which Gemini treats with the HIGHEST priority, above all
        user-turn text.  This forces Gemini to internalize the formula as
        its core identity rather than treating it as one instruction among many.
        """
        return f"""You are an elite professional scriptwriter creating YouTube voice-over scripts.

YOUR CONTENT FORMULA — THIS IS YOUR COMPLETE WRITING BLUEPRINT:
Read every line below. This formula defines exactly how you write every script:
the structure, the tone, the voice, the rhythm, the hook style, the story arc,
the promotion placement, the conclusion format — everything.

══════════════════════════════════════════════════════════════════════
{writing_guidelines}
══════════════════════════════════════════════════════════════════════

You follow this formula exactly. Not approximately — EXACTLY.
You do not invent your own structure on top of it.
You do not skip formula sections.
You execute each formula section in the correct order, with full creative energy.

NON-NEGOTIABLE OUTPUT RULES (override nothing — these are always active):
1. Write 100% in {language} — every single word, zero exceptions
2. Output ONLY plain flowing prose — no markdown, no **, no __, no ##
3. No section headers, labels, or dividers of any kind
4. No visual cues: VISUAL:, VIDEO:, SHOW:, CUT TO:, etc.
5. No narrator/speaker tags: NARRATOR:, SPEAKER:, HOST:, etc.
6. No timestamps: (0:00–0:15), (30 sec), (pause), etc.
7. No stage directions in brackets [ ] or parentheses ( )
8. No meta-commentary: "In this section…", "As I mentioned…", etc.
9. Never mention price, cost, or affordability
10. Start writing the script immediately — no preamble, no explanation"""

    def _build_chunk_prompt(
        self,
        title: str,
        niche: Dict,
        writing_guidelines: str,
        chunk: 'ChunkConfig',
        previous_context: str,
        total_chunks: int = 3
    ) -> str:
        """
        Build the user-turn prompt for one chunk.

        The formula already lives in the system instruction (highest priority).
        This prompt focuses entirely on chunk position, formula section mapping,
        and precise execution instructions.
        """
        language   = niche['language']
        niche_name = niche['name']
        product    = niche.get('product', 'our platform')

        pct_start = int(chunk.script_position_start * 100)
        pct_end   = int(chunk.script_position_end   * 100)

        if chunk.role == "HOOK_AND_FRAMEWORK":
            position_desc  = f"Chunk 1 of {total_chunks} — OPENING (0 % → {pct_end} % of the full script)"
            formula_task   = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the HOOK and OPENING of the script.\n"
                "Step 2 — MAP: Those opening formula sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                "         the hook style, the opening tone, the emotional trigger,\n"
                "         the sentence rhythm, the promise or tension to establish.\n"
                "Step 4 — LIMIT: Do NOT write anything from the middle or closing sections.\n"
                "         The script continues in the next chunks — do NOT conclude."
            )
            continuation_block = ""

        elif chunk.role == "DEEP_INSIGHTS_AND_EXAMPLES":
            position_desc  = f"Chunk {chunk.index} of {total_chunks} — MIDDLE BODY ({pct_start} % → {pct_end} % of the full script)"
            formula_task   = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the BODY / DEVELOPMENT / STORY EVENTS.\n"
                "Step 2 — MAP: Those body/development formula sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                "         the story progression, the emotional arc stages, the rhythm rules,\n"
                "         the number and placement of story events, any promotion rules that apply here.\n"
                "Step 4 — LIMIT: Do NOT re-write the hook (already done). Do NOT conclude.\n"
                "         The script ends in the next chunk — keep the tension alive."
            )
            continuation_block = (
                f"CONTINUE SEAMLESSLY FROM THE PREVIOUS CHUNK "
                f"(do NOT repeat or summarize what came before):\n"
                f'"...{previous_context}"\n\n'
            )

        else:  # IMPLEMENTATION_AND_CLOSE
            position_desc  = f"Chunk {chunk.index} of {total_chunks} — CLOSING ({pct_start} % → 100 % of the full script)"
            formula_task   = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the CLOSING, CONCLUSION, PROMOTION, and CTA.\n"
                "Step 2 — MAP: Those closing formula sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                "         the climax structure, the conclusion tone, the exact number of promotions,\n"
                "         how each promotion is written, the CTA format, the final sentence style.\n"
                "Step 4 — COMPLETE: This is the FINAL chunk. End the script fully and powerfully."
            )
            continuation_block = (
                f"CONTINUE SEAMLESSLY FROM THE PREVIOUS CHUNK "
                f"(do NOT repeat or summarize what came before):\n"
                f'"...{previous_context}"\n\n'
            )

        prompt = f"""SCRIPT CHUNK — EXECUTE YOUR FORMULA NOW

TITLE    : "{title}"
NICHE    : {niche_name}
LANGUAGE : {language}
POSITION : {position_desc}

{continuation_block}{formula_task}

━━━ CREATIVE EXECUTION ━━━
The formula defines your structure. Fill it with vivid, original content:
- Write specifically about "{title}" — not generic content
- Invent concrete, believable details: real-feeling examples, specific numbers,
  named characters if the formula uses them, emotional moments that feel lived-in
- Never sound like AI — sound like a world-class human storyteller
- Every sentence must earn its place

PRODUCT: {product}
Follow the formula's exact product placement rules.
NEVER mention price, cost, or affordability.

TOPIC LOCK: Every sentence must serve the title "{title}". Do not drift.

LENGTH: Write AT LEAST {chunk.target_chars:,} characters.
        Up to {int(chunk.target_chars * 1.08):,} characters is acceptable.
        Never cut short — use the full length to go deeper, not to pad.

START WRITING IN {language.upper()} NOW:"""

        return prompt

    def _extend_script(
        self,
        current_script: str,
        target_length: int,
        title: str,
        niche: dict,
        writing_guidelines: str,
        verbose: bool = False,
    ) -> str:
        """
        Continue the script until ≥ target_length chars.
        Uses the same system_instruction (formula) approach as the main chunks.
        """
        MAX_EXTEND_RETRIES = 2
        language   = niche.get('language', 'English')
        niche_name = niche.get('name', '')

        # Formula as system instruction — same approach as main chunks
        system_instruction = self._build_system_instruction(writing_guidelines, language)

        for attempt in range(MAX_EXTEND_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            extend_chars  = shortage + 1500
            extend_tokens = min(65536, max(int(extend_chars / 3 * 1.20) + 2000, 4000))
            tail = current_script[-600:].strip()

            prompt = f"""SCRIPT EXTENSION — CONTINUE THE BODY SECTION

TITLE   : "{title}"
NICHE   : {niche_name}
LANGUAGE: {language}

LAST PART OF SCRIPT (do NOT repeat — continue seamlessly from here):
"...{tail}"

━━━ FORMULA EXECUTION ━━━
Re-read your formula (in your system instructions).
Identify the BODY / DEVELOPMENT section rules that apply here.
Execute those rules now — continue the script body.

RULES:
- Write AT LEAST {extend_chars:,} characters of NEW, original content
- Do NOT repeat anything already in the script
- Do NOT add a conclusion or closing yet — this is body extension only
- Follow the formula's body section rhythm and structure exactly
- Start immediately — no preamble

START WRITING IN {language.upper()} NOW:"""

            try:
                model = genai.GenerativeModel(
                    'gemini-2.5-flash',
                    system_instruction=system_instruction
                )
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.85,
                        "max_output_tokens": extend_tokens,
                        "top_p": 0.95,
                        "top_k": 40,
                    }
                )
                extension = response.text.strip()
                current_script = current_script.rstrip() + ' ' + extension
                if verbose:
                    print(f"   Extension attempt {attempt + 1}: +{len(extension):,} chars → total {len(current_script):,}")
                time.sleep(4)
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

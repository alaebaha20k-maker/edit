#!/usr/bin/env python3
"""
Script Generator — Formula-First Architecture

The user's niche Writing Guidelines IS the complete law.
Every sentence must execute a specific rule from that formula.

Workflow:
  PHASE 1 — PLAN (gemini-2.5-flash, 1 call):
    Read the full Writing Guidelines.
    Extract every section in order WITH its actual rules/content from the formula.
    Assign sections+content to chunks. Lock anchor, promo count, CTA.
    *** KEY: section CONTENT (not just names) is stored in the plan ***

  PHASE 2–N — WRITE (gemini-2.5-pro, 1 call per chunk):
    System instruction = full Writing Guidelines (model identity = formula)
    Chunk prompt = specific section RULES extracted from formula (injected directly)
    The model has the formula both as identity AND as explicit rules per section.
    This guarantees compliance even for 40K-70K char formulas.

  PHASE FINAL — POST: Merge → strip stop → clean → dedup → length enforce.
"""

import json
import re
import time
import google.generativeai as genai
from typing import Dict, List, Optional
from config import Config
from niche_manager import NicheManager
from chunk_planner import ChunkPlanner
from settings_manager import SettingsManager
from utils import detect_language_from_text, get_language_name

STOP_SIGNAL = "=== END OF SCRIPT — DO NOT CONTINUE ==="


class ScriptGenerator3Chunk:

    def __init__(self):
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        self.api_key = api_key

    # =========================================================================
    # PUBLIC
    # =========================================================================

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 10000,
        verbose: bool = True,
    ) -> Dict:

        start_time = time.time()

        if not Config.validate_script_length(length):
            raise ValueError(
                f"Length must be between {Config.MIN_SCRIPT_LENGTH} "
                f"and {Config.MAX_SCRIPT_LENGTH}"
            )

        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        detected_lang_code = detect_language_from_text(title)
        detected_lang_name = get_language_name(detected_lang_code)
        original_niche_lang = niche.get("language", "English")
        niche["language"] = detected_lang_name

        formula  = niche["writing_guidelines"]
        language = niche["language"]
        product  = niche.get("product", "our platform")

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 FORMULA-FIRST SCRIPT GENERATION")
            print(f"{'='*70}")
            print(f"Title   : {title}")
            print(f"Target  : {length:,} chars")
            print(f"Niche   : {niche['name']}")
            print(f"Language: {language}" + (
                f" (detected, overrides niche: {original_niche_lang})"
                if detected_lang_name != original_niche_lang else ""))
            print(f"Models  : plan={Config.GEMINI_PLAN_MODEL}  write={Config.GEMINI_SCRIPT_MODEL}")
            print(f"{'='*70}\n")

        # ── Step 0: Plan chunks ───────────────────────────────────────────────
        planner      = ChunkPlanner(length)
        chunks       = planner.plan()
        total_chunks = len(chunks)

        if verbose:
            print(f"📦 Chunk Plan ({total_chunks} chunks):")
            for c in chunks:
                print(f"   Chunk {c.index}/{total_chunks}: {c.role} ({c.target_chars:,} chars)")
            print()

        # ── PHASE 1 — PLAN: Parse formula, extract section content ──────────────
        if verbose:
            print(f"🔧 PHASE 1 — PLAN")
            print(f"   Formula   : {len(formula):,} chars (Writing Guidelines)")
            print(f"   Parsing sections + extracting rules per chunk...")
        plan = self._parse_formula(title, formula, language, total_chunks, verbose)
        if verbose:
            print(f"   ✅ Anchor  : {plan.get('anchor', '—')}")
            print(f"   ✅ Promos  : {plan.get('promo_count', '—')}")
            print(f"   ✅ CTA     : {plan.get('cta_action', '—')}")
            for i, secs in plan.get("chunk_sections", {}).items():
                content_len = len(plan.get("chunk_section_content", {}).get(i, ""))
                print(f"   ✅ Chunk {i}  : {', '.join(secs)}  [{content_len:,} chars of rules injected]")
            print()

        # ── System instruction: full formula = model identity ─────────────────
        system_instruction = self._build_system_instruction(formula, language)

        # ── PHASE 2–N — WRITE each chunk ──────────────────────────────────────
        generated_chunks = []
        previous_context = ""
        promo_count_so_far = 0

        formula_chars = len(formula)
        for chunk in chunks:
            if verbose:
                print(f"✍️  PHASE {chunk.index + 1} — WRITE Chunk {chunk.index}/{total_chunks}: {chunk.role}...")
                print(f"   📋 Writing Guidelines injected into prompt: {formula_chars:,} chars")

            is_final = (chunk.index == total_chunks)

            prompt = self._build_chunk_prompt(
                title=title,
                language=language,
                product=product,
                chunk=chunk,
                total_chunks=total_chunks,
                plan=plan,
                previous_context=previous_context,
                promo_count_so_far=promo_count_so_far,
                is_final=is_final,
            )

            temp         = self._get_temperature(chunk.role)
            chunk_tokens = min(65536, max(int(chunk.target_chars / 3 * 1.25) + 2000, 4000))

            chunk_text = self._call_api(
                prompt=prompt,
                system_instruction=system_instruction,
                model_name=Config.GEMINI_SCRIPT_MODEL,
                temperature=temp,
                max_output_tokens=chunk_tokens,
                target_chars=chunk.target_chars,
                label=f"Chunk {chunk.index}/{total_chunks}",
                verbose=verbose,
            )

            # Count promo tags placed so far
            promo_count_so_far += len(re.findall(
                r'\[PROMO\s*#?\d*\s*[—\-]?\s*START\]', chunk_text, re.IGNORECASE
            ))

            generated_chunks.append(chunk_text)
            if verbose:
                print(f"   ✅ {len(chunk_text):,} chars (raw)")

            if chunk.index < total_chunks:
                sents = [s.strip() for s in re.split(r'[.!?]', chunk_text) if len(s.strip()) > 15]
                previous_context = (
                    ". ".join(sents[-3:]) + "."
                    if len(sents) >= 3
                    else chunk_text[-300:]
                )
                time.sleep(4)

        # ── Post-processing ───────────────────────────────────────────────────
        if verbose:
            print(f"\n🔗 Merging {len(generated_chunks)} chunks...")
        full_script = self._merge_chunks(generated_chunks)
        full_script = self._clean_script(full_script)            # strips stop signal first
        full_script = self._remove_duplicate_sentences(full_script, verbose=verbose)

        # ── Length enforcement ────────────────────────────────────────────────
        # Overshoot tolerance: 1 % of target (min 300, max 2000 chars).
        # This prevents trimming a 100K script that comes out at 100,500 chars.
        MAX_OVERSHOOT = max(300, min(int(length * 0.01), 2000))
        char_count    = len(full_script)
        if verbose:
            print(f"\n📏 Length: {char_count:,} / {length:,} target  (tolerance: +{MAX_OVERSHOOT:,})")

        if char_count < length:
            shortage_pct = round((length - char_count) / length * 100, 1)
            if verbose:
                print(f"   ⚠️  Short by {length - char_count:,} chars ({shortage_pct}%) — extending...")
            full_script = self._extend_script(
                current_script=full_script,
                target_length=length,
                title=title,
                niche=niche,
                formula=formula,
                plan=plan,
                verbose=verbose,
            )
            full_script = self._clean_script(full_script)
            char_count  = len(full_script)
            if verbose:
                print(f"   ✅ After extension: {char_count:,} chars")

        if char_count > length + MAX_OVERSHOOT:
            if verbose:
                print(f"   ✂️  Over by {char_count - length:,} chars — trimming to sentence boundary...")
            full_script = self._trim_to_length(full_script, length + MAX_OVERSHOOT)
            char_count  = len(full_script)
            if verbose:
                print(f"   ✅ After trim: {char_count:,} chars")

        validation      = self._validate_script(full_script, title, length)
        char_count      = len(full_script)
        word_count      = len(full_script.split())
        generation_time = time.time() - start_time

        if verbose:
            print(f"\n📊 FINAL STATS:")
            print(f"   Characters : {char_count:,}")
            print(f"   Words      : {word_count:,}")
            print(f"   Target     : {length:,}  (delta: {char_count - length:+,})")
            print(f"   Time       : {generation_time:.1f}s")
            print(f"   Valid      : {validation['valid']}")
            if not validation["valid"]:
                print(f"   Errors     : {', '.join(validation['errors'])}")
            print(f"{'='*70}\n")

        return {
            "script"     : full_script,
            "stats"      : {"chars": char_count, "words": word_count, "time": generation_time},
            "validation" : validation,
            "chunks_used": len(chunks),
        }

    # =========================================================================
    # STEP 0 — FORMULA PARSER
    # =========================================================================

    def _parse_formula(
        self,
        title: str,
        formula: str,
        language: str,
        total_chunks: int,
        verbose: bool = False,
    ) -> dict:
        """
        PHASE 1 — PLAN

        Reads the full Writing Guidelines and produces a concrete execution plan:
        - Identify every section in order
        - Assign sections to chunks
        - Extract the ACTUAL RULES/CONTENT from the formula for each chunk
          (this is the critical upgrade — section content injected into writing prompts)
        - Lock: anchor, promo count, CTA

        The plan's chunk_section_content dict holds the verbatim formula rules
        for each chunk. These get injected directly into writing prompts so the
        model has the specific formula rules RIGHT IN FRONT OF IT while writing,
        not buried in a 42K system instruction it has to "look up."
        """
        # ── Build the dynamic chunk format block for any number of chunks ──────
        chunk_roles = {1: "opening / hook", total_chunks: "closing / CTA"}
        chunk_format_block = ""
        for i in range(1, total_chunks + 1):
            role_hint = chunk_roles.get(i, "body / development")
            if i == 1:
                sections_hint = "<hook section(s)>"
            elif i == total_chunks:
                sections_hint = "<closing section(s) | CTA section(s)>"
            else:
                sections_hint = "<body section(s)>"
            chunk_format_block += (
                f"CHUNK{i}: {sections_hint}  ({role_hint})\n"
                f"CHUNK{i}_CONTENT:\n"
                f"[For CHUNK{i}: Write a complete, detailed writing brief. Include:\n"
                f" 1. TONE & STYLE rules from the Writing Guidelines for these sections\n"
                f" 2. STRUCTURE: the exact sequence / steps to follow\n"
                f" 3. MANDATORY PHRASES or hooks to use (copy verbatim from guidelines)\n"
                f" 4. SPECIFIC TECHNIQUES (storytelling, hooks, transitions, etc.)\n"
                f" 5. WHAT TO INCLUDE (topics, arguments, examples required)\n"
                f" 6. WHAT TO AVOID for these sections\n"
                f"Do NOT summarize vaguely. Copy the actual rules word-for-word.]\n"
                f"END_CHUNK{i}\n\n"
            )

        prompt = f"""You are an expert script production planner. Your job is to read the Writing Guidelines below and produce a CONCRETE EXECUTION PLAN that a script writer can follow directly.

TITLE: "{title}"
LANGUAGE: {language}
NUMBER OF CHUNKS TO WRITE: {total_chunks}
(Chunk 1 = opening/hook, Chunk {total_chunks} = closing/CTA, middle chunks = body content)

════════════════════════ WRITING GUIDELINES ════════════════════════
{formula}
════════════════════════════════════════════════════════════════════

OUTPUT the plan below. Use EXACTLY this format. No markdown, no JSON.

SECTIONS: <all section names from Writing Guidelines, pipe-separated, in order>

{chunk_format_block}ANCHOR: <the main subject, person, or story anchor — infer from title>
PROMO_COUNT: <integer — how many promotion/ad blocks the Writing Guidelines prescribes. 0 if none.>
CTA: <the exact call-to-action text prescribed in the Writing Guidelines>
CLOSING: <how the Writing Guidelines says to close the video>

CRITICAL RULES:
- CHUNK{{}}_CONTENT blocks MUST contain real, specific, actionable rules — not summaries like "follow the guidelines"
- Copy mandatory phrases VERBATIM from the Writing Guidelines
- Each CHUNK_CONTENT block should be detailed enough that a writer can follow it WITHOUT reading the original guidelines
- PROMO_COUNT must be 0 if the Writing Guidelines has no promotional section
- Every CHUNK block (CHUNK1 through CHUNK{total_chunks}) MUST be present in your output"""

        def _parse_response(text: str, total_chunks: int, title: str) -> dict:
            """Parse the response including multi-line CHUNK{i}_CONTENT blocks."""
            text_upper = text.upper()   # for case-insensitive marker search

            # --- Parse single-line fields ONLY outside CHUNK_CONTENT blocks ---
            # BUG FIX: if we parse ALL lines, a line like "PROMO_COUNT: 1" inside
            # a CHUNK_CONTENT block (copied from Writing Guidelines) would override
            # the real PROMO_COUNT. So we track whether we're inside a block.
            lines = text.strip().splitlines()
            line_map: Dict[str, str] = {}
            inside_content_block = False
            for line in lines:
                line_stripped = line.strip()
                line_upper_s  = line_stripped.upper()
                # Detect entering a content block
                if any(line_upper_s.startswith(f"CHUNK{i}_CONTENT") for i in range(1, total_chunks + 1)):
                    inside_content_block = True
                    continue
                # Detect leaving a content block
                if any(line_upper_s.startswith(f"END_CHUNK{i}") for i in range(1, total_chunks + 1)):
                    inside_content_block = False
                    continue
                # Skip all lines inside content blocks
                if inside_content_block:
                    continue
                # Parse scalar key: value lines
                if ":" in line_stripped:
                    key, _, val = line_stripped.partition(":")
                    k = key.strip().upper()
                    line_map[k] = val.strip()

            # --- Parse multi-line CHUNK{i}_CONTENT blocks (case-insensitive) ---
            chunk_section_content: Dict[str, str] = {}
            for i in range(1, total_chunks + 1):
                start_marker = f"CHUNK{i}_CONTENT:"
                end_marker   = f"END_CHUNK{i}"
                # Case-insensitive search
                start_idx = text_upper.find(start_marker.upper())
                end_idx   = text_upper.find(end_marker.upper())
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    content = text[start_idx + len(start_marker):end_idx].strip()
                    if content and len(content) > 50:   # must have real content
                        chunk_section_content[str(i)] = content

            # --- Sections ---
            raw_sections = line_map.get("SECTIONS", "")
            sections = [s.strip() for s in raw_sections.split("|") if s.strip()] if raw_sections else []

            # --- Chunk section name assignments ---
            chunk_sections: Dict[str, List[str]] = {}
            for i in range(1, total_chunks + 1):
                raw = line_map.get(f"CHUNK{i}", "")
                secs = [s.strip() for s in raw.split("|") if s.strip()]
                if not secs:
                    secs = [sections[i - 1]] if i <= len(sections) else [f"Part {i}"]
                chunk_sections[str(i)] = secs

            # --- Scalar fields ---
            anchor    = line_map.get("ANCHOR", title).strip() or title
            promo_raw = line_map.get("PROMO_COUNT", "NOT_FOUND").strip()
            # Debug: show exactly what Gemini returned for PROMO_COUNT
            if verbose:
                print(f"   🔍 PROMO_COUNT raw from Gemini: '{promo_raw}'")
            try:
                digits = re.sub(r"[^\d]", "", promo_raw)
                promo_count = int(digits) if digits else 0
            except ValueError:
                promo_count = 0
            cta_action = line_map.get("CTA", "subscribe and hit the bell").strip()
            closing    = line_map.get("CLOSING", "conclude with the subscribe call to action").strip()

            return {
                "sections"             : sections,
                "chunk_sections"       : chunk_sections,
                "chunk_section_content": chunk_section_content,   # ← verbatim rules per chunk
                "_formula_text"        : formula,                 # ← stored for fallback injection
                "anchor"               : anchor,
                "promo_count"          : promo_count,
                "cta_action"           : cta_action,
                "closing_note"         : closing,
            }

        try:
            if verbose:
                print(f"   📤 Sending to Gemini Flash: {len(prompt):,} chars total")
                print(f"      └─ Writing Guidelines inside: {len(formula):,} chars")

            model    = genai.GenerativeModel(Config.GEMINI_PLAN_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.05, "max_output_tokens": 32768},
            )
            text = response.text.strip()

            if verbose:
                print(f"   📥 Gemini Flash response: {len(text):,} chars")

            plan = _parse_response(text, total_chunks, title)

            # Report content extraction results
            if verbose:
                content_map = plan.get("chunk_section_content", {})
                if not content_map:
                    print("   ⚠️  Section content blocks not found in response — full formula will be injected into chunk prompts as fallback")
                else:
                    for ci, cv in content_map.items():
                        print(f"   ✅ Chunk {ci} rules extracted: {len(cv):,} chars")
                print(f"   ✅ Promos  : {plan['promo_count']}")

            return plan

        except Exception as e:
            if verbose:
                print(f"   ⚠️  Formula parse failed ({e}) — fallback plan (formula still in system instruction)")
            fallback_sections = [f"Part {i+1}" for i in range(total_chunks)]
            return {
                "sections"             : fallback_sections,
                "chunk_sections"       : {str(i): [fallback_sections[i - 1]] for i in range(1, total_chunks + 1)},
                "chunk_section_content": {},
                "_formula_text"        : formula,   # fallback: full formula injected into prompts
                "anchor"               : title,
                "promo_count"          : 0,
                "cta_action"           : "subscribe and hit the bell",
                "closing_note"         : "conclude with the subscribe call to action",
            }

    # =========================================================================
    # SYSTEM INSTRUCTION — full Writing Guidelines as model identity
    # =========================================================================

    def _build_system_instruction(self, formula: str, language: str) -> str:
        """
        The Writing Guidelines go here — in the system instruction slot —
        which Gemini treats as the model's core identity.

        This sets WHO the model is. The chunk prompts tell it WHAT to write next
        (with the specific formula rules for that section injected directly).
        """
        return f"""YOU ARE A PROFESSIONAL SCRIPT WRITER. YOUR ENTIRE WRITING STYLE, STRUCTURE, TONE, AND CONTENT RULES ARE DEFINED BY THE WRITING GUIDELINES BELOW. YOU MUST EXECUTE THEM WITH ABSOLUTE PRECISION.

THESE WRITING GUIDELINES ARE YOUR COMPLETE LAW:
══════════════════════════════════════════════════════════════════════════════════════
{formula}
══════════════════════════════════════════════════════════════════════════════════════

HOW TO APPLY THESE GUIDELINES:
- Every sentence you write MUST execute a specific rule from the guidelines above.
- Follow the section structure EXACTLY as prescribed.
- Use the exact tone, hooks, phrases, and techniques specified.
- Do NOT invent a different structure or style — follow the formula.
- If the guidelines say to use a specific phrase or story: USE IT.
- If the guidelines specify a sequence of steps: FOLLOW that sequence.

OUTPUT FORMAT (applies to all chunks):
1. Write 100% in {language} — every word, no exceptions.
2. Plain prose only — no markdown, no **, no __, no ##, no bullet points in the script.
3. No visual directions: VISUAL:, VIDEO:, SHOW:, CUT TO:
4. No speaker/narrator labels: NARRATOR:, SPEAKER:, HOST:
5. No timestamps or time markers.
6. No stage directions in brackets [ ] or parentheses ( ).
7. No meta-commentary about the script.
8. Start directly with the first word of content.
9. After the final CTA line, STOP immediately."""

    # =========================================================================
    # CHUNK PROMPT — minimal, formula-first
    # =========================================================================

    def _build_chunk_prompt(
        self,
        title: str,
        language: str,
        product: str,
        chunk,
        total_chunks: int,
        plan: dict,
        previous_context: str,
        promo_count_so_far: int,
        is_final: bool,
    ) -> str:

        anchor       = plan.get("anchor", title)
        promo_count  = plan.get("promo_count", 0)
        cta_action   = plan.get("cta_action", "subscribe and hit the bell")
        sections_now = plan.get("chunk_sections", {}).get(str(chunk.index), [])

        # ── Build the sections directive for this chunk ────────────────────────
        # Strategy:
        #   • The FULL Writing Guidelines already live in the system_instruction
        #     (the model's core identity set before every generate_content call).
        #   • Here we inject ONLY the extracted section-specific rules so the
        #     prompt stays short and focused — long formulas repeated here make
        #     the model treat the guidelines as boilerplate noise.
        #   • If extraction failed, we inject just the section names + a hard
        #     directive to execute the system-instruction guidelines exactly.
        section_content = plan.get("chunk_section_content", {}).get(str(chunk.index), "")
        sections_label = " | ".join(sections_now) if sections_now else f"part {chunk.index} of {total_chunks}"

        if section_content:
            # Focused extracted rules for this chunk — the key directive
            sections_block = (
                f"SECTIONS TO WRITE FOR THIS CHUNK: {sections_label}\n\n"
                f"EXACT RULES FROM YOUR WRITING GUIDELINES FOR THESE SECTIONS:\n"
                f"{'═' * 60}\n"
                f"{section_content}\n"
                f"{'═' * 60}\n"
                f"Execute EVERY rule above verbatim. Your full Writing Guidelines are in your identity — apply them all."
            )
        else:
            # Fallback: no extracted content — direct the model to use its identity
            full_formula = plan.get("_formula_text", "")
            if full_formula:
                sections_block = (
                    f"SECTIONS TO WRITE: {sections_label}\n\n"
                    f"YOUR WRITING GUIDELINES (execute ALL rules exactly):\n"
                    f"{'═' * 60}\n"
                    f"{full_formula}\n"
                    f"{'═' * 60}"
                )
            else:
                sections_block = (
                    f"SECTIONS TO WRITE: {sections_label}\n"
                    f"Execute ALL rules from your Writing Guidelines (system identity) exactly."
                )

        # ── Continuation context ───────────────────────────────────────────────
        if previous_context:
            continuation = (
                f"CONTINUE SEAMLESSLY (do NOT repeat what was already written):\n"
                f'"...{previous_context}"\n\n'
            )
        else:
            continuation = ""

        # ── Promo counter ──────────────────────────────────────────────────────
        if promo_count == 0:
            promo_reminder = ""  # No promos in this formula — don't mention them
        elif chunk.index > 1:
            remaining = promo_count - promo_count_so_far
            promo_reminder = (
                f"PROMO COUNTER: {promo_count_so_far}/{promo_count} promo block(s) written. "
                f"Place exactly {remaining} more in this chunk per the Writing Guidelines.\n"
                f"PRODUCT: {product}\n\n"
            ) if remaining > 0 else (
                f"PROMO COUNTER: All {promo_count} promo block(s) done. Do NOT add more.\n\n"
            )
        else:
            promo_reminder = f"PRODUCT: {product}\n\n" if promo_count > 0 else ""

        # ── Final chunk stop rule ──────────────────────────────────────────────
        if is_final:
            stop_instruction = (
                f"\nHARD STOP: After writing the final CTA ('{cta_action}'), write this exact line:\n"
                f"{STOP_SIGNAL}\n"
                f"Then output NOTHING. Script complete.\n"
            )
            chunk_role_note = (
                f"FINAL CHUNK — write the closing and CTA exactly as prescribed in the Writing Guidelines."
            )
        else:
            stop_instruction = ""
            chunk_role_note = (
                f"Chunk {chunk.index} of {total_chunks}. "
                f"Do NOT write the closing or CTA yet — those come in the final chunk."
            )

        prompt = f"""═══ CHUNK {chunk.index}/{total_chunks} ═══

VIDEO TITLE: "{title}"
ANCHOR / SUBJECT: {anchor}
LANGUAGE: {language.upper()} — write every single word in {language}

{sections_block}

{continuation}{promo_reminder}YOUR ROLE FOR THIS CHUNK: {chunk_role_note}

MANDATORY: Apply your Writing Guidelines (in your identity) to every sentence.
LENGTH: Write at least {chunk.target_chars:,} characters (up to {int(chunk.target_chars * 1.08):,} max).
{stop_instruction}
START WRITING NOW:"""

        return prompt

    # =========================================================================
    # API CALL HELPER
    # =========================================================================

    def _call_api(
        self,
        prompt: str,
        system_instruction: str,
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        target_chars: int,
        label: str = "",
        verbose: bool = False,
    ) -> str:
        MAX_API_RETRIES   = 3
        MAX_SHORT_RETRIES = 2

        for short_attempt in range(MAX_SHORT_RETRIES + 1):
            for attempt in range(MAX_API_RETRIES + 1):
                try:
                    model = genai.GenerativeModel(
                        model_name,
                        system_instruction=system_instruction,
                    )
                    response = model.generate_content(
                        prompt,
                        generation_config={
                            "temperature"      : temperature,
                            "max_output_tokens": max_output_tokens,
                            "top_p"            : 0.95,
                            "top_k"            : 40,
                        },
                    )
                    break
                except Exception as e:
                    err = str(e)
                    is_quota = (
                        "429" in err
                        or "quota" in err.lower()
                        or "ResourceExhausted" in type(e).__name__
                    )
                    if not is_quota or attempt == MAX_API_RETRIES:
                        raise
                    m    = re.search(r"seconds: (\d+)", err)
                    wait = int(m.group(1)) + 5 if m else 35
                    if verbose:
                        print(f"   ⚠️  Quota — waiting {wait}s "
                              f"(attempt {attempt + 1}/{MAX_API_RETRIES})...")
                    time.sleep(wait)

            text    = response.text.strip()
            min_ok  = int(target_chars * 0.50)
            if len(text) >= min_ok or short_attempt == MAX_SHORT_RETRIES:
                return text
            if verbose:
                print(f"   ⚠️  {label} too short ({len(text):,} < {min_ok:,}) "
                      f"— retrying (attempt {short_attempt + 1}/{MAX_SHORT_RETRIES})...")
            time.sleep(4)

        return text

    # =========================================================================
    # EXTENSION (if merged script is short)
    # =========================================================================

    def _extend_script(
        self,
        current_script: str,
        target_length: int,
        title: str,
        niche: dict,
        formula: str,
        plan: dict,
        verbose: bool = False,
    ) -> str:
        """
        Extend the script until it reaches target_length.
        Loops up to MAX_RETRIES times, each time requesting enough chars to close
        the remaining gap. The full Writing Guidelines are injected into every
        extension prompt so the formula continues to be applied.
        """
        MAX_RETRIES = 6   # enough for even large shortages on 100K scripts
        language    = niche.get("language", "English")
        anchor      = plan.get("anchor", title)
        body_secs   = plan.get("sections", [])
        # Middle sections hint (exclude first and last — those are hook/close)
        mid_secs = body_secs[1:-1] if len(body_secs) > 2 else body_secs
        body_hint = (
            "Continue these body sections from the Writing Guidelines: " + ", ".join(mid_secs)
        ) if mid_secs else "Continue the body / development sections prescribed by your Writing Guidelines."

        system_instruction = self._build_system_instruction(formula, language)

        for attempt in range(MAX_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            # Request the exact shortage + a small buffer so one call can close it
            extend_chars  = shortage + 2000
            extend_tokens = min(65536, max(int(extend_chars / 3 * 1.3) + 3000, 6000))
            tail          = current_script[-800:].strip()

            prompt = f"""══════════ WRITING GUIDELINES (execute ALL rules) ══════════
{formula}
════════════════════════════════════════════════════════════

SCRIPT EXTENSION — TITLE: "{title}"
SUBJECT: {anchor}

CONTINUE FROM HERE (do NOT repeat what was already written):
"...{tail}"

TASK: {body_hint}
You must write at least {extend_chars:,} characters of new content.
Apply the Writing Guidelines exactly — same tone, style, structure, and rules.
Do NOT write a conclusion or CTA in this extension.

WRITE IN {language.upper()} NOW:"""

            try:
                extension = self._call_api(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model_name=Config.GEMINI_SCRIPT_MODEL,
                    temperature=0.85,
                    max_output_tokens=extend_tokens,
                    target_chars=extend_chars,
                    label=f"Extension {attempt + 1}/{MAX_RETRIES}",
                    verbose=verbose,
                )
                current_script = current_script.rstrip() + "\n\n" + extension.strip()
                new_total = len(current_script)
                if verbose:
                    remaining = max(0, target_length - new_total)
                    print(f"   Extension {attempt+1}: +{len(extension):,} chars → total {new_total:,} / {target_length:,}  (still need: {remaining:,})")
                time.sleep(4)
            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Extension {attempt + 1} failed: {e}")
                break

        return current_script

    # =========================================================================
    # POST-PROCESSING
    # =========================================================================

    def _merge_chunks(self, chunks: List[str]) -> str:
        merged = " ".join(chunks)
        merged = re.sub(r"(?i)(continuing from|as we discussed|as mentioned earlier)", "", merged)
        merged = re.sub(r"(?i)(in the previous (section|part|chunk))", "", merged)
        merged = re.sub(r"  +", " ", merged)
        return merged.strip()

    def _clean_script(self, text: str) -> str:
        # Strip everything at/after the hard stop signal FIRST
        idx = text.find(STOP_SIGNAL)
        if idx != -1:
            text = text[:idx]

        # Markdown
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
        text = re.sub(r"\*\*(.+?)\*\*",     r"\1", text)
        text = re.sub(r"\*(.+?)\*",          r"\1", text)
        text = re.sub(r"__(.+?)__",          r"\1", text)
        text = re.sub(r"_(.+?)_",            r"\1", text)
        text = re.sub(r"`(.+?)`",            r"\1", text)
        text = re.sub(r"#{1,6}\s+",          "",    text)
        text = re.sub(r"\*",                 "",    text)

        # Labels / cues
        text = re.sub(r"(?i)(VISUAL|VIDEO|NARRATOR|SPEAKER|SHOW|CUT TO)\s*:", "", text)

        # Timestamps
        text = re.sub(r"\(\s*\d+:\d+\s*-\s*\d+:\d+\s*\)", "", text)
        text = re.sub(r"\(\s*\d+\s*(sec|min|seconds?|minutes?)\s*\)", "", text)

        # Brackets / parentheses with directions
        text = re.sub(r"\[.+?\]", "", text)
        text = re.sub(r"\(.+?\)", "", text)

        # Spacing
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"  +",    " ",    text)

        return text.strip()

    def _remove_duplicate_sentences(self, text: str, verbose: bool = False) -> str:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        seen: set = set()
        unique: List[str] = []
        removed = 0

        for sent in sentences:
            norm = re.sub(r"[^\w\s]", "", sent.lower())
            norm = re.sub(r"\s+", " ", norm).strip()

            if len(norm) < 40:
                unique.append(sent)
                continue

            if norm in seen:
                removed += 1
                continue

            seen.add(norm)
            unique.append(sent)

        if verbose and removed:
            print(f"   🧹 Duplicate scanner: removed {removed} sentence(s)")

        return " ".join(unique)

    def _trim_to_length(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        last = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
        if last > max_chars * 0.8:
            return truncated[:last + 1].strip()
        return truncated.strip()

    def _get_temperature(self, role: str) -> float:
        return {
            "HOOK_AND_FRAMEWORK"        : 0.90,
            "DEEP_INSIGHTS_AND_EXAMPLES": 0.85,
            "IMPLEMENTATION_AND_CLOSE"  : 0.80,
        }.get(role, 0.85)

    def _validate_script(self, script: str, title: str, target_length: int) -> Dict:
        errors = []
        actual = len(script)

        if actual < target_length:
            errors.append(f"Too short: {actual:,} < {target_length:,}")
        elif actual > target_length + 300:
            errors.append(f"Too long: {actual:,} > {target_length + 300:,}")

        forbidden = [
            (r"(?i)\bVISUAL\s*:",       "VISUAL: label found"),
            (r"(?i)\bNARRATOR\s*:",     "NARRATOR: label found"),
            (r"\(\s*\d+:\d+",           "Timestamp found"),
            (re.escape(STOP_SIGNAL),    "Stop signal leaked into output"),
        ]
        for pattern, msg in forbidden:
            if re.search(pattern, script):
                errors.append(msg)

        title_words = [w.lower() for w in title.split() if len(w) > 3]
        if title_words:
            found = sum(1 for w in title_words if w in script.lower())
            if found < len(title_words) * 0.3:
                errors.append("Possible topic drift (title words missing)")

        return {"valid": len(errors) == 0, "errors": errors}

#!/usr/bin/env python3
"""
Script Generator — Two-Prompt Architecture (PRODUCTION)

Workflow per video:
  Prompt 0  — Planning call (gemini-2.5-flash, cheap & fast)
              Locks in: historical anchor, promo count, section order, CTA text.
              Result is a concise JSON plan that is injected into every writing chunk.

  Prompts 1…N — Writing chunks (gemini-2.5-pro, highest quality)
              Each chunk receives the plan so it never forgets the anchor or
              loses count of promotions.  The final chunk gets a hard STOP
              signal so the AI never restarts a second script.

  Post-processing — Programmatic duplicate sentence scanner + stop-signal strip.

API call count: 1 (plan) + N chunks (writing) + 0–2 (extension if short)
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

# The line the model MUST write at the very end — nothing after it is kept.
STOP_SIGNAL = "=== END OF SCRIPT — DO NOT CONTINUE ==="


class ScriptGenerator3Chunk:
    """
    Production script generator — two-prompt, pro-model architecture.
    """

    def __init__(self):
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        self.api_key = api_key

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────────

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 10000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate a script using the two-prompt workflow.

        Returns dict with: script, stats, validation, chunks_used
        """
        start_time = time.time()

        if not Config.validate_script_length(length):
            raise ValueError(
                f"Length must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH}"
            )

        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        detected_lang_code = detect_language_from_text(title)
        detected_lang_name = get_language_name(detected_lang_code)
        original_niche_lang = niche.get('language', 'English')
        niche['language'] = detected_lang_name

        writing_guidelines = niche['writing_guidelines']
        language           = niche['language']

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 SCRIPT GENERATION — TWO-PROMPT ARCHITECTURE")
            print(f"{'='*70}")
            print(f"Title   : {title}")
            print(f"Target  : {length:,} chars")
            print(f"Niche   : {niche['name']}")
            print(f"Language: {language}" +
                  (f" (detected, overrides niche: {original_niche_lang})"
                   if detected_lang_name != original_niche_lang else ""))
            print(f"Models  : plan={Config.GEMINI_PLAN_MODEL}  write={Config.GEMINI_SCRIPT_MODEL}")
            print(f"{'='*70}\n")

        # ── PROMPT 0 — PLANNING ───────────────────────────────────────────────
        if verbose:
            print("📋 PROMPT 0 — Planning call (locks anchor + promo count)...")
        plan = self._run_planning_call(title, writing_guidelines, language, verbose)
        if verbose:
            print(f"   Anchor   : {plan.get('anchor', '—')}")
            print(f"   Promos   : {plan.get('promo_count', '—')}")
            print(f"   CTA      : {plan.get('cta_action', '—')}")
            print(f"   Hook type: {plan.get('opening_hook_type', '—')}\n")

        # ── CHUNK PLAN ────────────────────────────────────────────────────────
        planner     = ChunkPlanner(length)
        chunks      = planner.plan()
        total_chunks = len(chunks)

        if verbose:
            print(f"📦 Chunk Plan ({total_chunks} chunks):")
            for c in chunks:
                print(f"   Chunk {c.index}/{total_chunks}: {c.role} ({c.target_chars:,} chars)")
            print()

        # ── SYSTEM INSTRUCTION (formula as model identity) ────────────────────
        system_instruction = self._build_system_instruction(writing_guidelines, language)

        # ── PROMPTS 1…N — WRITING CHUNKS ──────────────────────────────────────
        generated_chunks  = []
        previous_context  = ""
        promo_count_so_far = 0

        for chunk in chunks:
            if verbose:
                print(f"✍️  Writing Chunk {chunk.index}/{total_chunks}: {chunk.role}...")

            prompt = self._build_chunk_prompt(
                title=title,
                niche=niche,
                chunk=chunk,
                previous_context=previous_context,
                total_chunks=total_chunks,
                plan=plan,
                promo_count_so_far=promo_count_so_far,
            )

            temp        = self._get_temperature(chunk.role)
            chunk_tokens = min(65536, max(int(chunk.target_chars / 3 * 1.25) + 2000, 4000))

            chunk_text = self._call_api_with_retry(
                prompt=prompt,
                system_instruction=system_instruction,
                model_name=Config.GEMINI_SCRIPT_MODEL,
                temperature=temp,
                max_output_tokens=chunk_tokens,
                target_chars=chunk.target_chars,
                label=f"Chunk {chunk.index}/{total_chunks}",
                verbose=verbose,
            )

            # Count promo blocks written so far (for next chunk's counter)
            promo_count_so_far += len(re.findall(
                r'\[PROMO\s*#?\d+\s*[—\-]?\s*START\]', chunk_text, re.IGNORECASE
            ))

            generated_chunks.append(chunk_text)

            if verbose:
                print(f"   ✅ {len(chunk_text):,} chars (raw)")

            # Context for next chunk — last 3 sentences
            if chunk.index < total_chunks:
                sents = [s.strip() for s in re.split(r'[.!?]', chunk_text) if len(s.strip()) > 15]
                previous_context = '. '.join(sents[-3:]) + '.' if len(sents) >= 3 else chunk_text[-300:]
                time.sleep(4)

        # ── MERGE + CLEAN ──────────────────────────────────────────────────────
        if verbose:
            print(f"\n🔗 Merging {len(generated_chunks)} chunks...")
        full_script = self._merge_chunks(generated_chunks)
        full_script = self._clean_script(full_script)
        full_script = self._remove_duplicate_sentences(full_script, verbose=verbose)

        # ── LENGTH ENFORCEMENT ─────────────────────────────────────────────────
        MAX_OVERSHOOT = 300
        char_count    = len(full_script)

        if verbose:
            print(f"\n📏 Length: {char_count:,} / {length:,} target")

        if char_count < length:
            if verbose:
                print(f"   ⚠️  Short by {length - char_count:,} — extending...")
            full_script = self._extend_script(
                current_script=full_script,
                target_length=length,
                title=title,
                niche=niche,
                writing_guidelines=writing_guidelines,
                plan=plan,
                verbose=verbose,
            )
            full_script = self._clean_script(full_script)
            char_count  = len(full_script)
            if verbose:
                print(f"   ✅ After extension: {char_count:,} chars")

        if char_count > length + MAX_OVERSHOOT:
            if verbose:
                print(f"   ✂️  Over by {char_count - length:,} — trimming...")
            full_script = self._trim_to_length(full_script, length + MAX_OVERSHOOT)
            char_count  = len(full_script)
            if verbose:
                print(f"   ✅ After trim: {char_count:,} chars")

        # ── VALIDATE ───────────────────────────────────────────────────────────
        validation     = self._validate_script(full_script, title, length)
        char_count     = len(full_script)
        word_count     = len(full_script.split())
        generation_time = time.time() - start_time

        if verbose:
            print(f"\n📊 FINAL STATS:")
            print(f"   Characters : {char_count:,}")
            print(f"   Words      : {word_count:,}")
            print(f"   Target     : {length:,}")
            print(f"   Delta      : {char_count - length:+,}")
            print(f"   Time       : {generation_time:.1f}s")
            print(f"   Valid      : {validation['valid']}")
            if not validation['valid']:
                print(f"   Errors     : {', '.join(validation['errors'])}")
            print(f"{'='*70}\n")

        return {
            'script'     : full_script,
            'stats'      : {'chars': char_count, 'words': word_count, 'time': generation_time},
            'validation' : validation,
            'chunks_used': len(chunks),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # PROMPT 0 — PLANNING CALL
    # ─────────────────────────────────────────────────────────────────────────

    def _run_planning_call(
        self,
        title: str,
        writing_guidelines: str,
        language: str,
        verbose: bool = False,
    ) -> dict:
        """
        Fast planning call using gemini-2.5-flash.
        Returns a JSON plan that is injected into every writing chunk prompt.
        Locking the plan BEFORE writing prevents the anchor from being forgotten
        and prevents the promo counter from drifting mid-output.
        """
        prompt = f"""You are planning a YouTube voice-over script. Read the formula below carefully.

TITLE: "{title}"
LANGUAGE: {language}

FORMULA:
{writing_guidelines}

Your task: extract the script plan from the formula and title. Reply ONLY with a valid JSON object — no explanation, no markdown, no code fences.

{{
  "anchor": "<The exact historical person / story / event this script will center on — pick based on the title>",
  "promo_count": <integer — the exact number of promotional blocks the formula requires>,
  "promo_trigger": "<The exact formula moment / phrase that signals each promotion>",
  "cta_action": "<The final action the formula requires the viewer to take — e.g. 'subscribe and hit the bell'>",
  "opening_hook_type": "<One sentence describing the hook technique from the formula>",
  "body_sections": ["<section name 1>", "<section name 2>", "..."],
  "closing_structure": "<One sentence describing how the formula closes the script>"
}}

Output ONLY the JSON. Nothing before or after."""

        try:
            model    = genai.GenerativeModel(Config.GEMINI_PLAN_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.10, "max_output_tokens": 1024},
            )
            text = response.text.strip()
            # Strip code fences if the model wrapped the JSON
            text = re.sub(r'```(?:json)?\s*', '', text).strip('` \n')
            plan = json.loads(text)
            return plan
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Planning call failed ({e}) — using safe defaults")
            return {
                "anchor"          : "historical figure from the title",
                "promo_count"     : 2,
                "promo_trigger"   : "natural transition point",
                "cta_action"      : "subscribe and hit the bell",
                "opening_hook_type": "tension-based opening",
                "body_sections"   : ["main events", "analysis", "lessons"],
                "closing_structure": "conclusion with subscribe CTA",
            }

    # ─────────────────────────────────────────────────────────────────────────
    # SYSTEM INSTRUCTION
    # ─────────────────────────────────────────────────────────────────────────

    def _build_system_instruction(self, writing_guidelines: str, language: str) -> str:
        """
        The niche content formula is placed in the system instruction slot —
        Gemini gives this the HIGHEST priority, above any user-turn text.
        """
        return f"""You are an elite professional scriptwriter creating YouTube voice-over scripts.

YOUR CONTENT FORMULA — THIS IS YOUR COMPLETE WRITING BLUEPRINT:
Read every line below. This formula defines EVERYTHING about how you write:
structure, tone, voice, rhythm, hook style, story arc, promo placement, conclusion.

══════════════════════════════════════════════════════════════════════
{writing_guidelines}
══════════════════════════════════════════════════════════════════════

You follow this formula EXACTLY. Not approximately — EXACTLY.
You do not invent your own structure on top of it.
You do not skip formula sections.
You execute each formula section in the correct order, with full creative energy.

NON-NEGOTIABLE OUTPUT RULES (always active — nothing overrides these):
1.  Write 100% in {language} — every single word, zero exceptions.
2.  Output ONLY plain flowing prose — no markdown, no **, no __, no ##.
3.  No section headers, labels, or dividers of any kind.
4.  No visual cues: VISUAL:, VIDEO:, SHOW:, CUT TO:, etc.
5.  No narrator/speaker tags: NARRATOR:, SPEAKER:, HOST:, etc.
6.  No timestamps: (0:00–0:15), (30 sec), (pause), etc.
7.  No stage directions in brackets [ ] or parentheses ( ).
8.  No meta-commentary: "In this section…", "As I mentioned…", etc.
9.  Never mention price, cost, or affordability.
10. Start writing the script immediately — no preamble, no explanation.
11. ONE script only. After the final CTA line, STOP. Do not restart."""

    # ─────────────────────────────────────────────────────────────────────────
    # CHUNK PROMPT BUILDER
    # ─────────────────────────────────────────────────────────────────────────

    def _build_chunk_prompt(
        self,
        title: str,
        niche: Dict,
        chunk: 'ChunkConfig',
        previous_context: str,
        total_chunks: int,
        plan: dict,
        promo_count_so_far: int,
    ) -> str:
        language   = niche['language']
        niche_name = niche['name']
        product    = niche.get('product', 'our platform')

        pct_start = int(chunk.script_position_start * 100)
        pct_end   = int(chunk.script_position_end   * 100)

        # ── Plan context block (injected into every chunk) ───────────────────
        anchor       = plan.get('anchor', 'the historical figure from the title')
        promo_count  = plan.get('promo_count', 2)
        promo_trigger = plan.get('promo_trigger', '')
        cta_action   = plan.get('cta_action', 'subscribe and hit the bell')
        closing_desc  = plan.get('closing_structure', 'conclusion with CTA')

        plan_block = (
            f"━━━ LOCKED SCRIPT PLAN (do not deviate) ━━━\n"
            f"Historical anchor : {anchor}\n"
            f"Total promo blocks: {promo_count} (formula-mandated)\n"
            f"Promos written so far in earlier chunks: {promo_count_so_far}\n"
            f"Promo trigger     : {promo_trigger}\n"
            f"Final CTA action  : {cta_action}\n"
            f"Closing structure : {closing_desc}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        # ── Role-specific instructions ────────────────────────────────────────
        if chunk.role == "HOOK_AND_FRAMEWORK":
            position_desc = f"Chunk 1 of {total_chunks} — OPENING (0 % → {pct_end} % of the full script)"
            formula_task  = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the HOOK and OPENING.\n"
                "Step 2 — MAP: Those opening sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                f"         hook style = {plan.get('opening_hook_type', 'tension-based')},\n"
                "         opening tone, emotional trigger, sentence rhythm, promise/tension.\n"
                "Step 4 — LIMIT: Do NOT write anything from middle or closing sections.\n"
                "         Do NOT conclude. The script continues in the next chunks."
            )
            continuation_block = ""
            stop_block = ""

        elif chunk.role == "DEEP_INSIGHTS_AND_EXAMPLES":
            position_desc = (
                f"Chunk {chunk.index} of {total_chunks} — "
                f"MIDDLE BODY ({pct_start} % → {pct_end} % of the full script)"
            )
            remaining_promos = promo_count - promo_count_so_far
            formula_task  = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the BODY / DEVELOPMENT / STORY EVENTS.\n"
                "Step 2 — MAP: Those body/development sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                "         story progression, emotional arc stages, rhythm rules,\n"
                "         number and placement of story events, any promo rules that apply here.\n"
                f"Step 4 — PROMO COUNTER: You still need {remaining_promos} more promo block(s).\n"
                "         Place them ONLY at the formula-specified trigger moments.\n"
                "         Tag them exactly as the formula instructs (e.g. [PROMO #X — START]).\n"
                "Step 5 — LIMIT: Do NOT re-write the hook. Do NOT conclude yet.\n"
                "         Keep the tension alive — the script ends in the next chunk."
            )
            continuation_block = (
                f"CONTINUE SEAMLESSLY FROM THE PREVIOUS CHUNK "
                f"(do NOT repeat or summarize what came before):\n"
                f'"...{previous_context}"\n\n'
            )
            stop_block = ""

        else:  # IMPLEMENTATION_AND_CLOSE
            position_desc = (
                f"Chunk {chunk.index} of {total_chunks} — "
                f"CLOSING ({pct_start} % → 100 % of the full script)"
            )
            remaining_promos = promo_count - promo_count_so_far
            formula_task  = (
                "━━━ FORMULA EXECUTION FOR THIS CHUNK ━━━\n"
                "Step 1 — PARSE: Re-read the formula in your system instructions.\n"
                "         Identify the section(s) that define the CLOSING, CONCLUSION, PROMOTION, and CTA.\n"
                "Step 2 — MAP: Those closing sections are what you write RIGHT NOW.\n"
                "Step 3 — EXECUTE: Follow every rule in those sections to the letter:\n"
                "         climax structure, conclusion tone,\n"
                f"         EXACTLY {remaining_promos} more promo block(s) — no more, no less,\n"
                f"         CTA action = '{cta_action}', final sentence style.\n"
                "Step 4 — COMPLETE: This is the FINAL chunk. End the script fully and powerfully.\n"
                "Step 5 — HARD STOP: After you have written the final CTA / subscribe line,\n"
                f"         write this exact line on its own and then STOP COMPLETELY:\n"
                f"         {STOP_SIGNAL}\n"
                "         Nothing after that line. No summary. No new hook. No restart.\n"
                "         ONE script. ONE ending."
            )
            continuation_block = (
                f"CONTINUE SEAMLESSLY FROM THE PREVIOUS CHUNK "
                f"(do NOT repeat or summarize what came before):\n"
                f'"...{previous_context}"\n\n'
            )
            stop_block = (
                f"\n⚠️  STOP RULE: The instant you write the final CTA line, write:\n"
                f"   {STOP_SIGNAL}\n"
                f"   Then output NOTHING else. You are done."
            )

        prompt = f"""SCRIPT CHUNK — EXECUTE YOUR FORMULA NOW

TITLE    : "{title}"
NICHE    : {niche_name}
LANGUAGE : {language}
POSITION : {position_desc}

{plan_block}

{continuation_block}{formula_task}

━━━ CREATIVE EXECUTION ━━━
The formula defines your structure. Fill it with vivid, original content:
- Center the script around: {anchor}
- Write specifically about "{title}" — not generic content
- Invent concrete, believable details: real-feeling examples, specific numbers,
  named characters if the formula uses them, emotional moments that feel lived-in
- Never sound like AI — sound like a world-class human storyteller
- Every sentence must earn its place

PRODUCT : {product}
Follow the formula's exact product placement rules.
NEVER mention price, cost, or affordability.

TOPIC LOCK: Every sentence must serve the title "{title}". Do not drift.

LENGTH: Write AT LEAST {chunk.target_chars:,} characters.
        Up to {int(chunk.target_chars * 1.08):,} characters is acceptable.
        Never cut short — use the full length to go deeper, not to pad.
{stop_block}
START WRITING IN {language.upper()} NOW:"""

        return prompt

    # ─────────────────────────────────────────────────────────────────────────
    # API CALL HELPER — retry on quota errors, re-request if too short
    # ─────────────────────────────────────────────────────────────────────────

    def _call_api_with_retry(
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
        MAX_API_RETRIES  = 3
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
                        '429' in err
                        or 'quota' in err.lower()
                        or 'ResourceExhausted' in type(e).__name__
                    )
                    if not is_quota or attempt == MAX_API_RETRIES:
                        raise
                    m = re.search(r'seconds: (\d+)', err)
                    wait = int(m.group(1)) + 5 if m else 35
                    if verbose:
                        print(f"   ⚠️  Quota — waiting {wait}s "
                              f"(attempt {attempt + 1}/{MAX_API_RETRIES})...")
                    time.sleep(wait)

            text = response.text.strip()

            min_ok = int(target_chars * 0.50)
            if len(text) >= min_ok or short_attempt == MAX_SHORT_RETRIES:
                return text
            if verbose:
                print(f"   ⚠️  {label} too short "
                      f"({len(text):,} < {min_ok:,}) — retrying "
                      f"(attempt {short_attempt + 1}/{MAX_SHORT_RETRIES})...")
            time.sleep(4)

        return text

    # ─────────────────────────────────────────────────────────────────────────
    # EXTENSION (if script is short after merge)
    # ─────────────────────────────────────────────────────────────────────────

    def _extend_script(
        self,
        current_script: str,
        target_length: int,
        title: str,
        niche: dict,
        writing_guidelines: str,
        plan: dict,
        verbose: bool = False,
    ) -> str:
        MAX_EXTEND_RETRIES = 2
        language   = niche.get('language', 'English')
        niche_name = niche.get('name', '')
        anchor     = plan.get('anchor', 'the historical figure from the title')

        system_instruction = self._build_system_instruction(writing_guidelines, language)

        for attempt in range(MAX_EXTEND_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            extend_chars  = shortage + 1500
            extend_tokens = min(65536, max(int(extend_chars / 3 * 1.25) + 2000, 4000))
            tail          = current_script[-600:].strip()

            prompt = f"""SCRIPT EXTENSION — CONTINUE THE BODY SECTION

TITLE   : "{title}"
NICHE   : {niche_name}
LANGUAGE: {language}
ANCHOR  : {anchor}

LAST PART OF SCRIPT (do NOT repeat — continue seamlessly from here):
"...{tail}"

━━━ FORMULA EXECUTION ━━━
Re-read your formula (in your system instructions).
Identify the BODY / DEVELOPMENT section rules that apply here.
Execute those rules now — continue the script body, staying on the anchor: {anchor}

RULES:
- Write AT LEAST {extend_chars:,} characters of NEW, original content
- Do NOT repeat anything already written
- Do NOT add a conclusion or closing yet — this is body extension only
- Follow the formula's body section rhythm and structure exactly
- Start immediately — no preamble

START WRITING IN {language.upper()} NOW:"""

            try:
                extension = self._call_api_with_retry(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model_name=Config.GEMINI_SCRIPT_MODEL,
                    temperature=0.85,
                    max_output_tokens=extend_tokens,
                    target_chars=extend_chars,
                    label=f"Extension {attempt + 1}",
                    verbose=verbose,
                )
                current_script = current_script.rstrip() + ' ' + extension
                if verbose:
                    print(f"   Extension +{len(extension):,} → total {len(current_script):,}")
                time.sleep(4)
            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Extension {attempt + 1} failed: {e}")
                break

        return current_script

    # ─────────────────────────────────────────────────────────────────────────
    # POST-PROCESSING
    # ─────────────────────────────────────────────────────────────────────────

    def _merge_chunks(self, chunks: List[str]) -> str:
        merged = ' '.join(chunks)
        merged = re.sub(r'(?i)(continuing from|as we discussed|as mentioned earlier)', '', merged)
        merged = re.sub(r'(?i)(in the previous (section|part|chunk))', '', merged)
        merged = re.sub(r'  +', ' ', merged)
        return merged.strip()

    def _clean_script(self, text: str) -> str:
        """
        Strip the stop signal, then remove all formatting artifacts.
        The stop signal strip MUST happen first so nothing after it leaks through.
        """
        # ── Hard stop — discard everything at and after the signal ────────────
        stop_idx = text.find(STOP_SIGNAL)
        if stop_idx != -1:
            text = text[:stop_idx]

        # ── Markdown ──────────────────────────────────────────────────────────
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*(.+?)\*\*',     r'\1', text)
        text = re.sub(r'\*(.+?)\*',          r'\1', text)
        text = re.sub(r'__(.+?)__',          r'\1', text)
        text = re.sub(r'_(.+?)_',            r'\1', text)
        text = re.sub(r'`(.+?)`',            r'\1', text)
        text = re.sub(r'#{1,6}\s+',          '',    text)
        text = re.sub(r'\*',                 '',    text)

        # ── Labels + cues ─────────────────────────────────────────────────────
        text = re.sub(r'(?i)(VISUAL|VIDEO|NARRATOR|SPEAKER|SHOW|CUT TO)\s*:', '', text)

        # ── Timestamps ────────────────────────────────────────────────────────
        text = re.sub(r'\(\s*\d+:\d+\s*-\s*\d+:\d+\s*\)', '', text)
        text = re.sub(r'\(\s*\d+\s*(sec|min|seconds?|minutes?)\s*\)', '', text)

        # ── Brackets / parentheses with directions ────────────────────────────
        text = re.sub(r'\[.+?\]', '', text)
        text = re.sub(r'\(.+?\)', '', text)

        # ── Spacing ───────────────────────────────────────────────────────────
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +',    ' ',    text)

        return text.strip()

    def _remove_duplicate_sentences(self, text: str, verbose: bool = False) -> str:
        """
        Programmatic pass: remove exact or near-exact duplicate sentences.
        A sentence is considered a duplicate if its normalized form matches
        a sentence already seen earlier in the text.
        This catches the main failure mode where the AI generates a second
        hook/intro after the conclusion.
        """
        # Split on sentence-ending punctuation followed by whitespace
        sentences = re.split(r'(?<=[.!?])\s+', text)
        seen: set = set()
        unique: List[str] = []
        removed = 0

        for sent in sentences:
            # Normalize: lowercase, collapse whitespace, strip punctuation
            norm = re.sub(r'[^\w\s]', '', sent.lower())
            norm = re.sub(r'\s+', ' ', norm).strip()

            # Skip very short sentences from dedup check (connectors, single words)
            if len(norm) < 40:
                unique.append(sent)
                continue

            if norm in seen:
                removed += 1
                continue

            seen.add(norm)
            unique.append(sent)

        if verbose and removed:
            print(f"   🧹 Duplicate scanner: removed {removed} duplicate sentence(s)")

        return ' '.join(unique)

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────

    def _trim_to_length(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        truncated    = text[:max_chars]
        last_sentence = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
        if last_sentence > max_chars * 0.8:
            return truncated[:last_sentence + 1].strip()
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
            (r'(?i)\bVISUAL\s*:',  'VISUAL: label found'),
            (r'(?i)\bNARRATOR\s*:', 'NARRATOR: label found'),
            (r'\(\s*\d+:\d+',      'Timestamp found'),
            (re.escape(STOP_SIGNAL), 'Stop signal leaked into output'),
        ]
        for pattern, msg in forbidden:
            if re.search(pattern, script):
                errors.append(msg)

        title_words = [w.lower() for w in title.split() if len(w) > 3]
        if title_words:
            found = sum(1 for w in title_words if w in script.lower())
            if found < len(title_words) * 0.3:
                errors.append("Possible topic drift (title words missing)")

        return {'valid': len(errors) == 0, 'errors': errors}

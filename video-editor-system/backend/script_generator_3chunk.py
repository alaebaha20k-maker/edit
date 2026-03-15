#!/usr/bin/env python3
"""
Script Generator — Formula-First Architecture

The user's niche formula IS the complete law.
The AI's only job is to execute it exactly, section by section.

Workflow:
  Step 0 — Parse (gemini-2.5-flash, 1 call):
    Read the formula. Extract every section heading in order.
    Assign sections to chunks so each chunk knows EXACTLY what to write.
    Also lock: anchor/subject, promo count, CTA text.

  Steps 1–N — Write (gemini-2.5-pro, 1 call per chunk):
    Each chunk receives only: the full formula + the exact sections assigned to it.
    No extra structure, no creative instructions on top — the formula handles all of that.
    Final chunk carries the hard-stop signal.

  Post — Merge → strip stop signal → clean → deduplicate → length enforce.
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

        # ── Step 0b: Parse formula → extract sections + assign to chunks ─────
        if verbose:
            print("📋 Step 0 — Parsing formula (locking sections, anchor, promo count)...")
        plan = self._parse_formula(title, formula, language, total_chunks, verbose)
        if verbose:
            print(f"   Anchor    : {plan.get('anchor', '—')}")
            print(f"   Promos    : {plan.get('promo_count', '—')}")
            print(f"   CTA       : {plan.get('cta_action', '—')}")
            for i, secs in plan.get("chunk_sections", {}).items():
                print(f"   Chunk {i}   : {', '.join(secs)}")
            print()

        # ── System instruction: formula as model identity ─────────────────────
        system_instruction = self._build_system_instruction(formula, language)

        # ── Steps 1–N: Write each chunk ───────────────────────────────────────
        generated_chunks = []
        previous_context = ""
        promo_count_so_far = 0

        for chunk in chunks:
            if verbose:
                print(f"✍️  Writing Chunk {chunk.index}/{total_chunks}: {chunk.role}...")

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

        # Length enforcement
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
                print(f"   ✂️  Over by {char_count - length:,} — trimming...")
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
        Read the formula and produce a concrete execution plan:
        - Extract every section heading (in order)
        - Assign sections to chunks (1 … total_chunks)
        - Lock anchor, promo count, CTA action

        This runs BEFORE any writing so the AI never forgets what it decided.
        Uses gemini-2.5-flash (cheap + fast — this is a parsing task, not writing).
        """
        chunk_keys = {str(i): f"chunk {i}" for i in range(1, total_chunks + 1)}
        chunk_keys_json = json.dumps(chunk_keys, ensure_ascii=False)

        prompt = f"""You are reading a YouTube script formula and creating a production plan.

TITLE: "{title}"
LANGUAGE: {language}
TOTAL CHUNKS TO WRITE: {total_chunks}

═══════════════════════ FORMULA ═══════════════════════
{formula}
═══════════════════════════════════════════════════════

Tasks:
1. List every section of this formula in order (use the exact heading names from the formula).
2. Distribute those sections across {total_chunks} chunks.
   - Chunk 1 = opening / hook sections
   - Chunk {total_chunks} = closing / CTA / conclusion sections
   - Middle chunks = body / development / story sections
   (If only 1 chunk, it gets all sections.)
3. Extract the main anchor (historical person, story, or event the script focuses on — infer from title + formula).
4. Count how many promotional blocks the formula requires.
5. Extract the final CTA action text the formula prescribes.

Reply with ONLY a valid JSON object — no explanation, no markdown, no code fences.

{{
  "sections": ["exact section heading 1", "exact section heading 2", "..."],
  "chunk_sections": {{
    "1": ["section heading A", "section heading B"],
    "2": ["section heading C", "..."],
    "{total_chunks}": ["last section heading", "..."]
  }},
  "anchor": "<main person / story / event>",
  "promo_count": <integer>,
  "cta_action": "<exact CTA text or action from formula>",
  "closing_note": "<one sentence: how the formula ends the script>"
}}"""

        try:
            model    = genai.GenerativeModel(Config.GEMINI_PLAN_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.05, "max_output_tokens": 2048},
            )
            text = response.text.strip()
            text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
            plan = json.loads(text)

            # Ensure all chunk keys exist
            for i in range(1, total_chunks + 1):
                key = str(i)
                if key not in plan.get("chunk_sections", {}):
                    plan.setdefault("chunk_sections", {})[key] = (
                        plan.get("sections", [f"Section {i}"])
                    )
            return plan

        except Exception as e:
            if verbose:
                print(f"   ⚠️  Formula parse failed ({e}) — using fallback plan")
            # Safe fallback: split sections evenly
            fallback_sections = [f"Part {i+1}" for i in range(total_chunks)]
            return {
                "sections"     : fallback_sections,
                "chunk_sections": {str(i): [fallback_sections[i - 1]] for i in range(1, total_chunks + 1)},
                "anchor"       : title,
                "promo_count"  : 1,
                "cta_action"   : "subscribe and hit the bell",
                "closing_note" : "conclude with the subscribe call to action",
            }

    # =========================================================================
    # SYSTEM INSTRUCTION — formula is the law, nothing overrides it
    # =========================================================================

    def _build_system_instruction(self, formula: str, language: str) -> str:
        """
        The formula is placed HERE — in the system instruction slot —
        which Gemini treats with the highest possible priority.
        We add only the minimum necessary output rules; the formula defines everything else.
        """
        return f"""YOUR FORMULA — THIS IS YOUR COMPLETE WRITING LAW. EXECUTE IT EXACTLY.

Every word you write must come from this formula. The structure, the tone, the sections,
the hook style, the story events, the promotion placement, the CTA — all defined below.
Do not add, remove, or change anything the formula prescribes.

══════════════════════════════════════════════════════════════════════
{formula}
══════════════════════════════════════════════════════════════════════

ABSOLUTE OUTPUT RULES — these only govern format, not content:
1.  Language: write 100% in {language} — every word, no exceptions.
2.  Plain prose only — no markdown, no **, no __, no ##, no headers.
3.  No visual directions: VISUAL:, VIDEO:, SHOW:, CUT TO:, etc.
4.  No speaker/narrator tags: NARRATOR:, SPEAKER:, HOST:, etc.
5.  No timestamps: (0:00–0:15), (30 sec), (pause), etc.
6.  No stage directions in [ ] or ( ).
7.  No meta-commentary: "In this section…", "As mentioned…", etc.
8.  Start with the first word of the script — no preamble or explanation.
9.  ONE script only. After the final CTA line: STOP. Do not restart."""

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
        promo_count  = plan.get("promo_count", 1)
        cta_action   = plan.get("cta_action", "subscribe and hit the bell")
        sections_now = plan.get("chunk_sections", {}).get(str(chunk.index), [])

        # Format the section list
        if sections_now:
            sections_block = "FORMULA SECTIONS TO WRITE IN THIS CHUNK:\n" + "\n".join(
                f"  → {s}" for s in sections_now
            )
        else:
            sections_block = "Write the appropriate portion of the formula for this chunk position."

        # Continuation context (empty for first chunk)
        if previous_context:
            continuation = (
                f"CONTINUE SEAMLESSLY (do NOT repeat what was already written):\n"
                f'"...{previous_context}"\n\n'
            )
        else:
            continuation = ""

        # Promo counter reminder (middle + final chunks)
        if chunk.index > 1:
            remaining = promo_count - promo_count_so_far
            promo_reminder = (
                f"PROMO COUNTER: {promo_count_so_far} promo block(s) already written. "
                f"You still need exactly {remaining} more in this chunk "
                f"(per formula — place at formula-specified trigger).\n"
                f"PRODUCT: {product}\n\n"
            ) if remaining > 0 else (
                f"PROMO COUNTER: All {promo_count} promo block(s) already written. "
                f"Do NOT add any more promotion in this chunk.\n\n"
            )
        else:
            promo_reminder = f"PRODUCT: {product}\n\n"

        # Hard stop for final chunk
        if is_final:
            stop_instruction = (
                f"\nHARD STOP RULE:\n"
                f"After you write the final CTA line ('{cta_action}'), immediately write this exact line:\n"
                f"{STOP_SIGNAL}\n"
                f"Then output NOTHING else. The script is complete. Do not add summaries, new sections, "
                f"or restart.\n"
            )
            chunk_role_note = (
                f"This is the FINAL CHUNK. Complete the script fully — "
                f"write the closing sections and the CTA exactly as the formula prescribes."
            )
        else:
            stop_instruction = ""
            chunk_role_note = (
                f"This is chunk {chunk.index} of {total_chunks}. "
                f"Do NOT write closing or CTA sections — those come in chunk {total_chunks}. "
                f"Keep the narrative going."
            )

        prompt = f"""SCRIPT CHUNK {chunk.index} OF {total_chunks}

TITLE: "{title}"
SUBJECT / ANCHOR: {anchor}

{sections_block}

{continuation}{promo_reminder}NOTE: {chunk_role_note}

LENGTH: Write at least {chunk.target_chars:,} characters (up to {int(chunk.target_chars * 1.08):,} is fine).
Do not cut short — go deep on the formula sections assigned above.
{stop_instruction}
WRITE IN {language.upper()} NOW:"""

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
        MAX_RETRIES = 2
        language    = niche.get("language", "English")
        anchor      = plan.get("anchor", title)
        body_secs   = plan.get("sections", [])
        body_hint   = (
            "Continue the body sections from the formula: "
            + ", ".join(body_secs[1:-1] or body_secs)
        ) if body_secs else "Continue the body/development sections from the formula."

        system_instruction = self._build_system_instruction(formula, language)

        for attempt in range(MAX_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            extend_chars  = shortage + 1500
            extend_tokens = min(65536, max(int(extend_chars / 3 * 1.25) + 2000, 4000))
            tail          = current_script[-600:].strip()

            prompt = f"""SCRIPT EXTENSION

TITLE   : "{title}"
SUBJECT : {anchor}

LAST PART ALREADY WRITTEN (continue from here — do NOT repeat):
"...{tail}"

TASK: {body_hint}
Write at least {extend_chars:,} new characters of body content.
Follow the formula exactly. Do NOT add a conclusion or CTA yet.

WRITE IN {language.upper()} NOW:"""

            try:
                extension = self._call_api(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model_name=Config.GEMINI_SCRIPT_MODEL,
                    temperature=0.85,
                    max_output_tokens=extend_tokens,
                    target_chars=extend_chars,
                    label=f"Extension {attempt + 1}",
                    verbose=verbose,
                )
                current_script = current_script.rstrip() + " " + extension
                if verbose:
                    print(f"   Extension +{len(extension):,} → total {len(current_script):,}")
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

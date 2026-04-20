#!/usr/bin/env python3
"""
Script Generator — Formula-DNA Architecture

The user's niche Writing Guidelines IS the complete law — any size, any length.
Every sentence must execute a specific rule from that formula.

Workflow:
  PHASE 1 — PLAN (Gemini, 1 call):
    Read the FULL Writing Guidelines (any size — 1K to 300K+ chars).
    Extract formula_dna: ALL laws organized into 10 categories
      (opening, tone, structure, mandatory phrases, forbidden words,
       storytelling, engagement, promo/CTA, language, niche-specific).
    Build per-chunk step-by-step recipe, specific to this title.
    Lock anchor, promo count, CTA.

  PHASE 1 — FAST PATH (when DNA is cached):
    Skip formula re-read. Load cached DNA.
    Run a compact outline-only call (title-specific, no formula re-read).
    Saves 15-30s per generation for the same niche.

  PHASE 2–N — WRITE (Gemini Pro, 1 call per chunk):
    Every chunk prompt contains (in order):
      → Formula Core (position-0): universal quality laws + chunk-specific rules
      → DNA summary (position-1): organized niche laws extracted in Phase 1
      → full raw Writing Guidelines (when formula ≤ 65K chars): belt-and-suspenders
      → step-by-step outline: specific recipe for this chunk
      → self-check block: quality gate the model must verify before outputting
    For large formulas (> 65K): DNA only (raw too large to inject per chunk).

  PHASE FINAL — POST: Merge → strip stop → clean → dedup → length enforce.
"""

import hashlib
import json
import re
import time
from pathlib import Path
import google.generativeai as genai
from typing import Dict, List, Optional
from config import Config
from niche_manager import NicheManager
from chunk_planner import ChunkPlanner
from settings_manager import SettingsManager
from utils import detect_language_from_text, get_language_name

STOP_SIGNAL = "=== END OF SCRIPT — DO NOT CONTINUE ==="

# ---------------------------------------------------------------------------
# Formula DNA cache — disk-based, keyed by MD5 of the niche formula text.
# When the same niche is used again, Phase 1 skips the full formula re-read
# and runs a compact outline-only call instead (saves 15–30 s per generation).
# ---------------------------------------------------------------------------
_DNA_CACHE_DIR = Path("./cache/formula_dna")
_DNA_MIN_CHARS = 1500   # minimum chars to consider a DNA extraction valid


def _formula_cache_key(formula: str) -> str:
    return hashlib.md5(formula.encode("utf-8")).hexdigest()


def _load_cached_dna(formula: str) -> str:
    """Return cached formula DNA for this formula text, or '' if not cached."""
    try:
        _DNA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _DNA_CACHE_DIR / f"{_formula_cache_key(formula)}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")).get("dna", "")
    except Exception:
        pass
    return ""


def _save_cached_dna(formula: str, dna: str) -> None:
    """Persist formula DNA to disk cache for future generations."""
    try:
        _DNA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = _DNA_CACHE_DIR / f"{_formula_cache_key(formula)}.json"
        path.write_text(json.dumps({"dna": dna, "formula_len": len(formula)}), encoding="utf-8")
    except Exception:
        pass


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
        provider: str = "gemini",   # "gemini" | "claude"
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
            if provider == "claude":
                print(f"Engine  : 🔮 Claude Sonnet (claude-sonnet-4-6) via api.gngn.my")
                print(f"          plan={Config.GEMINI_PLAN_MODEL} (outline)  write=claude-sonnet-4-6 (chunks)")
            else:
                print(f"Engine  : 🤖 Gemini  plan={Config.GEMINI_PLAN_MODEL}  write={Config.GEMINI_SCRIPT_MODEL}")
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

        # ── DNA cache check — skip full formula re-read when possible ─────────
        cached_dna = _load_cached_dna(formula)
        if cached_dna:
            if verbose:
                print(f"   ✅ Formula DNA cache HIT ({len(cached_dna):,} chars) — outline-only call")
            plan = self._parse_outlines_only(title, cached_dna, language, total_chunks, verbose)
        else:
            if verbose:
                print(f"   Parsing sections + extracting rules per chunk...")
            plan = self._parse_formula(title, formula, language, total_chunks, verbose)
            # Cache DNA so the next generation of the same niche is faster
            dna = plan.get("formula_dna", "")
            if len(dna) >= _DNA_MIN_CHARS:
                _save_cached_dna(formula, dna)
                if verbose:
                    print(f"   💾 Formula DNA cached ({len(dna):,} chars) — next run will be faster")

        # CRITICAL: Always keep the raw formula in plan regardless of DNA path.
        # _parse_outlines_only sets _formula_text="" to save memory, but the chunk
        # builder needs the raw formula to inject alongside DNA for small/medium formulas.
        # Without this, formula rules are silently dropped when DNA cache is used.
        if not plan.get("_formula_text"):
            plan["_formula_text"] = formula

        if verbose:
            outline_map = plan.get("chunk_section_content", {})
            status = f"{len(outline_map)}/{total_chunks} chunk outlines extracted"
            print(f"   Plan status: {status}")
            print()

        # ── System instruction: short format rules only (formula goes in user msg)
        system_instruction = self._build_system_instruction(language)

        # ── PHASE 2–N — WRITE each chunk ──────────────────────────────────────
        generated_chunks = []
        previous_context = ""
        promo_count_so_far = 0
        sections_done: List[str] = []   # sections already written — passed to each chunk

        formula_chars = len(formula)
        for chunk in chunks:
            if verbose:
                dna_preview = plan.get("formula_dna", "")
                dna_ok      = len(dna_preview) >= 1500
                print(f"✍️  PHASE {chunk.index + 1} — WRITE Chunk {chunk.index}/{total_chunks}: {chunk.role}...")
                print(f"   📋 Niche formula : {formula_chars:,} chars total")
                dual = formula_chars <= 65000
                if dna_ok:
                    dna_lines = len([l for l in dna_preview.split('\n') if l.strip()])
                    inject_note = (
                        f"+ full {formula_chars:,}-char formula also injected (dual-inject)"
                        if dual else "DNA only (formula > 65K)"
                    )
                    print(f"   ⚖️  Formula DNA  : {dna_lines} law-lines ({len(dna_preview):,} chars) — {inject_note}")
                else:
                    print(f"   ⚠️  DNA failed   : full raw formula ({formula_chars:,} chars) injected directly")
                if sections_done:
                    print(f"   ✅ Sections done : {', '.join(sections_done)}")

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
                sections_already_done=sections_done,
            )

            temp         = self._get_temperature(chunk.role)
            chunk_tokens = min(65536, max(int(chunk.target_chars / 3 * 1.25) + 2000, 4000))

            if provider == "claude":
                chunk_text = self._call_api_claude(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    target_chars=chunk.target_chars,
                    label=f"Chunk {chunk.index}/{total_chunks}",
                    verbose=verbose,
                )
            else:
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

            # Mark this chunk's sections as done so next chunk won't reopen them
            this_chunk_sections = plan.get("chunk_sections", {}).get(str(chunk.index), [])
            sections_done.extend(s for s in this_chunk_sections if s not in sections_done)

            if chunk.index < total_chunks:
                # Use last 500 chars as continuation context — gives the next chunk
                # enough sentence fragments to continue naturally without restarting.
                previous_context = chunk_text[-500:].strip()
                time.sleep(0.3)   # minimal inter-chunk gap (was 4s → 1s → 0.3s)

        # ── Post-processing ───────────────────────────────────────────────────
        if verbose:
            print(f"\n🔗 Merging {len(generated_chunks)} chunks...")
        full_script = self._merge_chunks(generated_chunks)
        full_script = self._clean_script(full_script)            # strips stop signal first
        full_script = self._cut_at_restart(                      # cuts if script restarts after CTA
            full_script, plan.get("cta_action", ""), verbose=verbose
        )
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
                sections_done=sections_done,
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
    # STEP 0-FAST — OUTLINE-ONLY (when DNA is cached)
    # =========================================================================

    def _parse_outlines_only(
        self,
        title: str,
        cached_dna: str,
        language: str,
        total_chunks: int,
        verbose: bool = False,
    ) -> dict:
        """
        Fast Phase 1 path: DNA already cached — only generate title-specific
        chunk outlines. No formula re-read → saves 15–30 s per generation.
        Uses a compact prompt (~5K tokens instead of 70K+).
        """
        chunk_roles = {1: "HOOK / OPENING", total_chunks: "CLOSING / CTA"}
        outline_format = ""
        for i in range(1, total_chunks + 1):
            role = chunk_roles.get(i, "BODY / DEVELOPMENT")
            if i == total_chunks:
                closing_extra = (
                    f"CLOSING RULES (mandatory for this chunk):\n"
                    f"  - Every step must BUILD toward the CTA — no new tangents, no new examples left unfinished.\n"
                    f"  - Use the formula's EXACT closing technique (emotional payoff, final takeaway, or summary beat).\n"
                    f"  - The last step before CTA must deliver the CLIMAX promised by the title.\n"
                    f"  - Final step = the exact CTA from the formula (copy verbatim).\n"
                    f"  - The script MUST feel 100%% complete — no trailing thoughts, no mid-sentence cuts.\n"
                )
            else:
                closing_extra = ""
            outline_format += (
                f"<chunk_{i}_sections>which formula sections go in chunk {i} (pipe-separated)</chunk_{i}_sections>\n"
                f"<chunk_{i}_outline>\n"
                f"STEP-BY-STEP writing recipe for Chunk {i} ({role}), 100% specific to title \"{title}\".\n"
                f"For each step: STEP N — what to write | TECHNIQUE — formula rule | MANDATORY — verbatim phrase\n"
                f"{closing_extra}"
                f"</chunk_{i}_outline>\n\n"
            )

        prompt = f"""You are a script outline generator.
The Formula DNA below contains ALL niche laws already extracted from the Writing Guidelines.
Use it to create chunk-specific writing recipes tailored to this exact title.

FORMULA DNA (complete niche laws):
{cached_dna}

VIDEO TITLE: "{title}"
LANGUAGE: {language}
CHUNKS: {total_chunks}  (chunk 1 = hook/opening, chunk {total_chunks} = closing/CTA)

Output the following XML structure. Do NOT add markdown or code blocks.

<sections>all section names from the DNA, pipe-separated</sections>
<anchor>main subject or story at the heart of this video title</anchor>
<promo_count>integer — how many [PROMO] blocks the DNA requires. 0 if none.</promo_count>
<cta>exact CTA text from the DNA verbatim</cta>

{outline_format}"""

        try:
            if verbose:
                print(f"   📤 Outline-only call ({len(prompt):,} chars, DNA cached)...")
            model    = genai.GenerativeModel(Config.GEMINI_PLAN_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 32768},
            )
            text = response.text.strip()
            if verbose:
                print(f"   📥 Outlines received: {len(text):,} chars")
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Outline-only call failed ({e}) — using cached DNA without outlines")
            # Minimal plan: DNA works as the laws_block per chunk
            fallback_secs = [f"Part {i}" for i in range(1, total_chunks + 1)]
            return {
                "sections"             : fallback_secs,
                "chunk_sections"       : {str(i): [fallback_secs[i - 1]] for i in range(1, total_chunks + 1)},
                "chunk_section_content": {},
                "_formula_text"        : "",
                "anchor"               : title,
                "promo_count"          : 0,
                "cta_action"           : "subscribe and hit the bell",
                "formula_dna"          : cached_dna,
                "closing_note"         : "close with subscribe CTA",
            }

        # Reuse same XML parsing logic as _parse_formula
        text = re.sub(r'```[^\n]*\n', '', text)
        text = re.sub(r'```', '', text)

        chunk_section_content: Dict[str, str] = {}
        chunk_sections: Dict[str, List[str]] = {}

        for i in range(1, total_chunks + 1):
            sec_m = re.search(rf'<chunk_{i}_sections>(.*?)</chunk_{i}_sections>', text, re.DOTALL | re.IGNORECASE)
            if sec_m:
                secs = [s.strip() for s in sec_m.group(1).strip().split("|") if s.strip()]
                if secs:
                    chunk_sections[str(i)] = secs
            out_m = re.search(rf'<chunk_{i}_outline>(.*?)</chunk_{i}_outline>', text, re.DOTALL | re.IGNORECASE)
            if out_m:
                content = out_m.group(1).strip()
                if content and len(content) > 80:
                    chunk_section_content[str(i)] = content

        def _xml(tag: str, fallback: str = "") -> str:
            m = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else fallback

        raw_sections = _xml("sections", "")
        sections = [s.strip() for s in raw_sections.split("|") if s.strip()] if raw_sections else []
        for i in range(1, total_chunks + 1):
            if str(i) not in chunk_sections:
                chunk_sections[str(i)] = [sections[i - 1]] if i <= len(sections) else [f"Part {i}"]

        anchor = _xml("anchor", title) or title
        try:
            promo_count = int(re.sub(r"[^\d]", "", _xml("promo_count", "0")) or "0")
        except ValueError:
            promo_count = 0
        cta_action  = _xml("cta", "subscribe and hit the bell") or "subscribe and hit the bell"

        return {
            "sections"             : sections,
            "chunk_sections"       : chunk_sections,
            "chunk_section_content": chunk_section_content,
            "_formula_text"        : "",   # restored to raw formula after this call (see generate_script)
            "anchor"               : anchor,
            "promo_count"          : promo_count,
            "cta_action"           : cta_action,
            "formula_dna"          : cached_dna,
            "closing_note"         : "close with subscribe CTA",
        }

    # =========================================================================
    # STEP 0 — FORMULA PARSER (full path, first generation per niche)
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
        PHASE 1 — PLAN (the critical step)

        Does NOT just extract rules — produces a PRESCRIPTIVE SCRIPT OUTLINE
        that is 100% specific to the title AND 100% derived from the Writing Guidelines.

        The outline tells the writing model EXACTLY what to write in each paragraph:
          - Which formula section it belongs to
          - What specific content to write (tailored to this title)
          - Mandatory phrases/hooks to use (copied from formula)
          - What technique/structure to apply
          - How to transition

        This converts a 40K generic formula into a 5K–10K actionable recipe
        that the writing model executes step by step — no interpretation needed.
        """
        chunk_roles = {1: "HOOK / OPENING", total_chunks: "CLOSING / CTA"}

        # Build per-chunk outline request using XML tags (Gemini respects these reliably)
        outline_format = ""
        for i in range(1, total_chunks + 1):
            role = chunk_roles.get(i, "BODY / DEVELOPMENT")
            if i == total_chunks:
                closing_extra = (
                    f"CLOSING RULES (mandatory for this chunk):\n"
                    f"  - Every step must BUILD toward the CTA — no new tangents, no unfinished examples.\n"
                    f"  - Use the formula's EXACT closing technique (emotional payoff, summary beat, final takeaway).\n"
                    f"  - The last body step must deliver the CLIMAX promised by the title.\n"
                    f"  - Final step = copy the exact CTA phrase from the Writing Guidelines VERBATIM.\n"
                    f"  - The script MUST feel 100%% complete — every sentence finished, no trailing thoughts.\n"
                )
            else:
                closing_extra = ""
            outline_format += (
                f"<chunk_{i}_sections>which formula sections go in chunk {i} (pipe-separated)</chunk_{i}_sections>\n"
                f"<chunk_{i}_outline>\n"
                f"Write a STEP-BY-STEP writing recipe for Chunk {i} ({role}).\n"
                f"MUST be 100% specific to the title \"{title}\" AND 100% derived from the Writing Guidelines.\n"
                f"For each step include:\n"
                f"  STEP N – what to write (specific content for this title, not generic)\n"
                f"  TECHNIQUE – exact formula technique/structure to use\n"
                f"  MANDATORY – any required phrase from guidelines (copy VERBATIM)\n"
                f"  TRANSITION – how to move to the next step\n"
                f"Do NOT say 'follow the guidelines'. Write the actual recipe.\n"
                f"{closing_extra}"
                f"</chunk_{i}_outline>\n\n"
            )

        prompt = f"""You are an elite YouTube script production analyst. Your job is TWO things:
1. Do a COMPLETE, EXHAUSTIVE analysis of the Writing Guidelines below.
2. Create a PRESCRIPTIVE SCRIPT OUTLINE for each writing chunk.

VIDEO TITLE: "{title}"
LANGUAGE: {language}
CHUNKS: {total_chunks}  (chunk 1 = hook/opening, chunk {total_chunks} = closing/CTA)

<writing_guidelines>
{formula}
</writing_guidelines>

════════════════════════════════════════════════════════════
OUTPUT the following XML structure EXACTLY.
Do NOT add markdown. Do NOT wrap in code blocks.
════════════════════════════════════════════════════════════

<sections>all section names from the Writing Guidelines, pipe-separated</sections>
<anchor>main subject, person, or story at the heart of this video title</anchor>
<promo_count>integer — how many [PROMO] ad blocks the guidelines require. 0 if none.</promo_count>
<cta>copy the exact CTA text from the Writing Guidelines verbatim</cta>

<formula_dna>
CRITICAL: This is the COMPLETE FORMULA DNA — a full extraction of EVERY law in the Writing Guidelines.
The script writer will use this as their primary reference. Be EXHAUSTIVE. Miss nothing.
The Writing Guidelines may be 70,000 characters — extract ALL of it into organized laws below.

## 1. OPENING LAWS
[How must every video open? Copy exact opening phrases/hooks verbatim from the formula.
What is the exact opening technique? Word-for-word if specified.]

## 2. TONE & VOICE LAWS
[Exact tone requirements. How should the writer speak to the viewer?
Active/passive? First/second person? Energy level? Register?
Copy exact tone descriptors from the formula verbatim.]

## 3. STRUCTURE LAWS
[Paragraph structure rules. Sentence length requirements.
How long is each section? What transitions are required?
Exact structural patterns — copy them.]

## 4. MANDATORY PHRASES & HOOKS
[List EVERY phrase/sentence that MUST appear verbatim in the script.
Copy each one exactly from the Writing Guidelines.
Include required hooks, transitions, engagement triggers.]

## 5. FORBIDDEN WORDS & PATTERNS
[List every word, phrase, pattern, or technique that is explicitly banned.
Copy exact forbidden terms from the formula.]

## 6. STORYTELLING & CONTENT LAWS
[What content rules does this formula require?
Story structure? Examples? Social proof? Data points?
Specific content requirements for body sections.]

## 7. ENGAGEMENT & RETENTION LAWS
[What techniques must be used to retain viewer?
Pattern interrupts? Questions? Cliffhangers? Open loops?
Copy exact engagement techniques from the formula.]

## 8. PROMO & CTA LAWS
[How must promotions be written? Exact promo format.
How must the CTA be delivered? Copy verbatim format.]

## 9. LANGUAGE & STYLE LAWS
[Word choice rules. Vocabulary requirements.
Formality level. Any language-specific rules for {language}.]

## 10. NICHE-SPECIFIC LAWS
[Any unique rules, techniques, or requirements specific to THIS niche/channel formula.
What makes this formula different from generic YouTube scripts?
Copy ALL unique elements verbatim.]

IMPORTANT: Every section above must be filled in detail.
If the Writing Guidelines specifies something — it goes here.
If it is not in the Writing Guidelines — write "Not specified."
</formula_dna>

{outline_format}
════════════════════════════════════════════════════════════
ANALYSIS RULES:
- formula_dna must be EXHAUSTIVE — extract EVERY rule, no shortcuts
- Copy mandatory phrases and forbidden words VERBATIM from the Writing Guidelines
- Each chunk outline must be CONCRETE — specific to this title, not generic
- mandatory phrases in outlines must be copied VERBATIM from the Writing Guidelines
- promo_count must be 0 if the Writing Guidelines has no promotional blocks
- ALL chunk tags (chunk_1 through chunk_{total_chunks}) must be present
════════════════════════════════════════════════════════════"""

        def _parse_plan_response(text: str) -> dict:
            """Parse the XML-format prescriptive outline response."""

            # Strip markdown code blocks if model added them
            text = re.sub(r'```[^\n]*\n', '', text)
            text = re.sub(r'```', '', text)

            # ── Extract per-chunk outlines using regex (XML tags) ─────────────
            chunk_section_content: Dict[str, str] = {}
            chunk_sections: Dict[str, List[str]] = {}

            for i in range(1, total_chunks + 1):
                # Extract sections tag
                sec_match = re.search(
                    rf'<chunk_{i}_sections>(.*?)</chunk_{i}_sections>',
                    text, re.DOTALL | re.IGNORECASE
                )
                if sec_match:
                    raw = sec_match.group(1).strip()
                    secs = [s.strip() for s in raw.split("|") if s.strip()]
                    if secs:
                        chunk_sections[str(i)] = secs

                # Extract outline tag
                out_match = re.search(
                    rf'<chunk_{i}_outline>(.*?)</chunk_{i}_outline>',
                    text, re.DOTALL | re.IGNORECASE
                )
                if out_match:
                    content = out_match.group(1).strip()
                    if content and len(content) > 80:
                        chunk_section_content[str(i)] = content

            # ── Extract scalar fields using XML tags ──────────────────────────
            def _xml(tag: str, fallback: str = "") -> str:
                m = re.search(rf'<{tag}>(.*?)</{tag}>', text, re.DOTALL | re.IGNORECASE)
                return m.group(1).strip() if m else fallback

            raw_sections = _xml("sections", "")
            sections = [s.strip() for s in raw_sections.split("|") if s.strip()] if raw_sections else []

            # Fill missing chunk_sections from sections list
            for i in range(1, total_chunks + 1):
                if str(i) not in chunk_sections:
                    chunk_sections[str(i)] = [sections[i - 1]] if i <= len(sections) else [f"Part {i}"]

            anchor    = _xml("anchor", title) or title
            promo_raw = _xml("promo_count", "0")
            if verbose:
                print(f"   🔍 PROMO_COUNT raw: '{promo_raw}'")
            try:
                digits = re.sub(r"[^\d]", "", promo_raw)
                promo_count = int(digits) if digits else 0
            except ValueError:
                promo_count = 0
            cta_action   = _xml("cta", "subscribe and hit the bell") or "subscribe and hit the bell"
            # formula_dna: complete, exhaustive extraction of ALL niche laws from the formula.
            # This replaces injecting the raw 70K formula into every chunk — the model
            # extracted every law once in PHASE 1; now each chunk gets organized laws.
            formula_dna  = _xml("formula_dna", "").strip()
            # Fallback: also accept old mandatory_laws tag if present
            if not formula_dna:
                formula_dna = _xml("mandatory_laws", "").strip()

            return {
                "sections"             : sections,
                "chunk_sections"       : chunk_sections,
                "chunk_section_content": chunk_section_content,
                "_formula_text"        : formula,
                "anchor"               : anchor,
                "promo_count"          : promo_count,
                "cta_action"           : cta_action,
                "formula_dna"          : formula_dna,
                "closing_note"         : "close with subscribe CTA",
            }

        try:
            if verbose:
                print(f"   📤 PHASE 1 — generating prescriptive outline (Pro model)...")
                print(f"      Formula: {len(formula):,} chars | Title: \"{title}\"")

            model    = genai.GenerativeModel(Config.GEMINI_PLAN_MODEL)
            # 65536 tokens: enough for exhaustive formula_dna extraction from 70K formula
            # + per-chunk outlines. This is the most important call — must not be truncated.
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.1, "max_output_tokens": 65536},
            )
            text = response.text.strip()

            if verbose:
                print(f"   📥 Plan response: {len(text):,} chars")

            plan = _parse_plan_response(text)

            if verbose:
                outline_map = plan.get("chunk_section_content", {})
                dna         = plan.get("formula_dna", "")
                if dna:
                    dna_lines = len([l for l in dna.split('\n') if l.strip()])
                    print(f"   ✅ Formula DNA    : {dna_lines} law-lines extracted ({len(dna):,} chars) — "
                          f"covers opening/tone/structure/phrases/forbidden/engagement/CTA")
                else:
                    print(f"   ⚠️  Formula DNA extraction failed — raw formula will be injected per chunk")
                if not outline_map:
                    print("   ⚠️  No outline extracted — full formula injected into every chunk prompt (fallback)")
                else:
                    for ci, cv in outline_map.items():
                        secs = ", ".join(plan["chunk_sections"].get(ci, []))
                        print(f"   ✅ Chunk {ci} outline : {len(cv):,} chars  [{secs}]")
                print(f"   ✅ Anchor         : {plan['anchor']}")
                print(f"   ✅ Promos         : {plan['promo_count']}")

            return plan

        except Exception as e:
            if verbose:
                print(f"   ⚠️  PHASE 1 failed ({e}) — fallback: full formula in every chunk prompt")
            fallback_sections = [f"Part {i+1}" for i in range(total_chunks)]
            return {
                "sections"             : fallback_sections,
                "chunk_sections"       : {str(i): [fallback_sections[i - 1]] for i in range(1, total_chunks + 1)},
                "chunk_section_content": {},
                "_formula_text"        : formula,
                "anchor"               : title,
                "promo_count"          : 0,
                "cta_action"           : "subscribe and hit the bell",
                "formula_dna"          : "",
                "closing_note"         : "close with subscribe CTA",
            }

    # =========================================================================
    # SYSTEM INSTRUCTION — short & focused (formula goes in user message)
    # =========================================================================

    def _build_system_instruction(self, language: str) -> str:
        return f"""You are an elite video script writer trained to execute niche formulas exactly.
Your ONLY job is to follow the Writing Guidelines and Formula Core given in the prompt.
You do not improvise style, structure, or tone. You execute the formula — sentence by sentence.

STYLE MANDATE (non-negotiable):
- Do NOT write like generic AI. Do NOT default to bland YouTube-style content.
- Do NOT use soft filler: "So today", "In this video we will", "Let me know in the comments".
- Do NOT use vague transitions, feel-good padding, or soft summaries.
- Write like someone sharing a secret — direct, specific, confident, formula-driven.
- Every sentence must be earned. Every paragraph must escalate or reveal something new.

OUTPUT FORMAT — strict:
1. Write 100% in {language} — every word, no exceptions.
2. Plain prose only. No markdown (**, __, ##). No bullet points.
3. No visual directions: VISUAL:, VIDEO:, SHOW:, CUT TO:
4. No speaker labels: NARRATOR:, HOST:, SPEAKER:
5. No timestamps. No stage directions. No meta-commentary.
6. Start with the first word of content. Nothing before it.
7. Stop immediately after the final CTA line."""

    # =========================================================================
    # FIX 2+4: FORMULA CORE — universal quality laws + chunk-specific rules
    # Injected at position-0 in every chunk prompt, before DNA and raw formula.
    # =========================================================================

    def _get_chunk_rules(self, chunk_index: int, total_chunks: int) -> str:
        """Chunk-position-specific writing rules (Fix 4)."""
        if chunk_index == 1:
            return (
                "  OPENING RULES:\n"
                "  • HOOK: Open with the highest-tension sentence possible. No warmup, no build-up.\n"
                "  • PAYLOAD EARLY: Reveal the core promise or mechanism within the first paragraph.\n"
                "  • CURIOSITY GAP: Create an open question the viewer MUST stay to answer.\n"
                "  • SETUP: Establish why this matters to THIS viewer, RIGHT NOW.\n"
                "  ✗ FORBIDDEN: greetings, 'today we will', 'in this video', slow warmups, 'imagine'."
            )
        elif chunk_index == total_chunks:
            return (
                "  CLOSING RULES:\n"
                "  • CONTENT FIRST: 90%+ of this chunk is REAL CONTENT — insights, payoff, resolution, depth.\n"
                "  • BYPASS: Proactively kill every remaining objection before the viewer thinks of it.\n"
                "  • PAYOFF: Deliver the full emotional/logical payoff the title promised — no shortcuts.\n"
                "  • FINAL STORY: Include one final concrete example, story beat, or case result that seals the point.\n"
                "  • RESIDUE LINE: One quotable, memorable sentence the viewer will replay in their head.\n"
                "  • CTA LAST: CTA comes ONLY at the very end — after all content is complete.\n"
                "  ✗ FORBIDDEN: jumping to CTA early, vague summaries, 'so there you have it', trailing thoughts, new topics."
            )
        else:
            mid_ratio = chunk_index / total_chunks
            if mid_ratio < 0.55:
                return (
                    "  EARLY-MIDDLE RULES:\n"
                    "  • MECHANISM: Explain HOW/WHY with specifics — not what, but the inside view.\n"
                    "  • PROOF: Add a concrete example, stat, or story within every major point.\n"
                    "  • ESCALATION: Each paragraph raises the stakes or reveals a new layer.\n"
                    "  • RETENTION HOOK: End on a partial reveal — make them need the next section.\n"
                    "  ✗ FORBIDDEN: generic explanations, summarizing what was already said."
                )
            else:
                return (
                    "  LATE-MIDDLE RULES:\n"
                    "  • DEPTH: Go deeper — this is where most scripts go shallow. Don't.\n"
                    "  • CONTRAST: Show what happens with vs. without — make stakes visceral.\n"
                    "  • MOMENTUM: Writing accelerates. Sentences get shorter. Energy rises.\n"
                    "  • BRIDGE: Set up the final section — leave the viewer leaning forward.\n"
                    "  ✗ FORBIDDEN: new setups without payoff, restating earlier points."
                )

    def _build_formula_core(self, chunk_index: int, total_chunks: int) -> str:
        """
        Compact universal quality laws + chunk-specific rules.
        Injected at position-0 in every chunk prompt (Fix 2 + Fix 4).
        These are the behavioral laws that enforce quality across all niches.
        """
        chunk_rules = self._get_chunk_rules(chunk_index, total_chunks)
        return (
            f"╔{'═' * 68}╗\n"
            f"║          FORMULA CORE — MANDATORY FOR EVERY SENTENCE IN THIS CHUNK         ║\n"
            f"╚{'═' * 68}╝\n"
            f"UNIVERSAL LAWS — check before writing each sentence:\n"
            f"  HOOK: First sentence of any section must grab. No preamble.\n"
            f"  PAYLOAD EARLY: Give the core value/mechanism in the first 20%% of this chunk.\n"
            f"  ESCALATION: Each paragraph must raise stakes. Never flatten. Never plateau.\n"
            f"  RETENTION: End every major beat with an open loop or 'wait for it' signal.\n"
            f"  SPECIFICITY: Replace every vague claim with a number, name, date, or fact.\n"
            f"  NO FILLER: Zero filler sentences. Every sentence must earn its place.\n"
            f"  NO REPETITION: Never restate what was said — unless adding entirely new value.\n"
            f"  STRONG LINES: At least one sentence per section the viewer will remember.\n"
            f"{'─' * 70}\n"
            f"STYLE LOCK:\n"
            f"  ✗ Do NOT write like generic AI. No bland YouTube voice.\n"
            f"  ✗ No soft summaries, vague transitions, or feel-good padding.\n"
            f"  ✗ Do NOT start sentences with: So, Now, Well, Basically, In other words, Remember.\n"
            f"  ✓ Sound like the formula's intended voice — direct, specific, confident.\n"
            f"  ✓ Write like someone who KNOWS and is sharing a secret, not explaining a concept.\n"
            f"{'─' * 70}\n"
            f"CHUNK {chunk_index}/{total_chunks} — POSITION-SPECIFIC RULES:\n"
            f"{chunk_rules}\n"
            f"{'═' * 70}\n\n"
        )

    def _build_self_check(self, chunk_index: int, total_chunks: int, is_final: bool) -> str:
        """
        Self-check block appended to every chunk prompt before 'WRITE NOW' (Fix 3).
        Forces the model to verify quality before outputting.
        """
        checks = [
            "No filler sentences (every sentence adds value or cut it)",
            "No vague claims (add number / name / fact to every vague statement)",
            "No repetition (no point restated from earlier without new value)",
            "Escalation intact (each paragraph raises stakes or reveals more)",
        ]
        if chunk_index == 1:
            checks.insert(0, "Hook strength: does the first sentence grab without warmup?")
            checks.insert(1, "Payload delivered: is the core mechanism in the first 20%%?")
        if is_final:
            checks.append("Closing body fills 90%+ of the chunk — not just a brief CTA?")
            checks.append("All 5 closing steps written: payoff, objection kill, final story, transformation, residue?")
            checks.append("Residue line: one quotable sentence the viewer will remember?")
            checks.append("CTA is exact and verbatim — placed LAST after all content?")
            checks.append("No vague summaries or 'that's all for today' filler?")
        else:
            checks.append("Open loop: does the ending make the viewer NEED to keep watching?")

        check_list = "\n".join(f"  ✓ {c}" for c in checks)
        return (
            f"\n{'─' * 70}\n"
            f"SELF-CHECK — verify BEFORE outputting:\n"
            f"{check_list}\n"
            f"If any check fails → rewrite that part internally first. Only output text that passes ALL checks.\n"
            f"{'─' * 70}\n"
        )

    # =========================================================================
    # CHUNK PROMPT — formula-first, self-checking
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
        sections_already_done: List[str] = None,
    ) -> str:

        anchor       = plan.get("anchor", title)
        full_formula = plan.get("_formula_text", "")
        formula_dna  = plan.get("formula_dna", "")
        promo_count  = plan.get("promo_count", 0)
        cta_action   = plan.get("cta_action", "subscribe and hit the bell")
        sections_now = plan.get("chunk_sections", {}).get(str(chunk.index), [])
        outline      = plan.get("chunk_section_content", {}).get(str(chunk.index), "")
        sections_label = " | ".join(sections_now) if sections_now else f"part {chunk.index} of {total_chunks}"

        # ── FORMULA BLOCK — adaptive based on formula size and DNA quality ────────
        #
        # CASE A — formula fits in context (≤ 65K chars):
        #   laws_block    = DNA at position-0 (organized priority summary)
        #   formula_block = FULL raw formula also injected — guarantees zero rules missed.
        #   DNA + raw formula together = maximum compliance. Gemini 2.5 handles this easily.
        #
        # CASE B — large formula (> 65K chars):
        #   laws_block    = DNA only (raw formula too large to inject per chunk)
        #   formula_block = EMPTY — DNA must cover everything
        #
        # CASE C — DNA extraction failed:
        #   laws_block    = empty
        #   formula_block = FULL raw formula — model reads it directly
        #
        # Why inject both for small/medium formulas: DNA compression loses specific rules.
        # A 42K formula compressed to 3K DNA can silently drop 90% of specific instructions.
        # Belt-and-suspenders: DNA for attention priority, raw formula for completeness.
        DNA_MIN_CHARS = 1500
        FORMULA_DUAL_INJECT_LIMIT = 65000   # inject both DNA + raw formula below this size

        dna_good     = len(formula_dna) >= DNA_MIN_CHARS
        formula_fits = full_formula and len(full_formula) <= FORMULA_DUAL_INJECT_LIMIT

        if dna_good:
            laws_block = (
                f"╔{'═' * 66}╗\n"
                f"║     NICHE FORMULA PRIORITY SUMMARY (extracted from Writing Guidelines)  ║\n"
                f"╚{'═' * 66}╝\n"
                f"Read this first — it highlights the MOST CRITICAL laws from your formula.\n"
                f"{'─' * 68}\n"
                f"{formula_dna}\n"
                f"{'─' * 68}\n"
                f"COMPLIANCE CHECK before writing each paragraph:\n"
                f"  ✓ Opening laws followed?  ✓ Tone correct?  ✓ Mandatory phrases used?\n"
                f"  ✓ Forbidden words avoided?  ✓ Structure correct?  ✓ Niche laws applied?\n\n"
            )
            if formula_fits:
                # Also inject full raw formula — belt-and-suspenders for medium formulas.
                # DNA compression can miss specific phrases/rules; raw formula ensures 100% coverage.
                formula_block = (
                    f"════════════════ COMPLETE WRITING GUIDELINES — EVERY RULE APPLIES ════════════════\n"
                    f"The formula above is a summary. THIS is the full law. All {len(full_formula):,} characters apply.\n"
                    f"Read every section. Every rule below is mandatory — summary above + full text here.\n"
                    f"{'─' * 68}\n"
                    f"{full_formula}\n"
                    f"{'─' * 68}\n"
                    f"END OF WRITING GUIDELINES — every sentence must execute a rule from above.\n"
                    f"{'═' * 68}\n\n"
                )
            else:
                formula_block = ""   # Large formula: DNA only (raw too large per chunk)

        elif full_formula:
            # DNA extraction failed — inject the raw formula as the primary reference
            laws_block = ""
            formula_block = (
                f"════════════════ YOUR WRITING GUIDELINES — READ EVERY RULE ════════════════\n"
                f"This is your niche formula. EVERY rule, law, phrase, and technique below\n"
                f"must be applied. The formula is {len(full_formula):,} characters — read it ALL.\n"
                f"{'─' * 68}\n"
                f"{full_formula}\n"
                f"{'─' * 68}\n"
                f"END OF WRITING GUIDELINES — every sentence must execute a rule from above.\n"
                f"{'═' * 68}\n\n"
            )
        else:
            laws_block    = ""
            formula_block = ""

        # ── Current section label ──────────────────────────────────────────────
        current_section_label = " | ".join(sections_now) if sections_now else f"part {chunk.index}"

        # ── Step-by-step outline for this chunk (MUST come first in prompt) ───
        # CRITICAL: The outline is the most specific instruction for this chunk.
        # It must be at the TOP of the prompt so the model gives it full attention.
        # The "lost in the middle" problem means anything buried after a long formula
        # gets ignored. Outline-first solves this.
        word_target = int(chunk.target_chars / 5.2)   # ~5.2 chars per word average
        if outline:
            task_block = (
                f"════════════════ CHUNK {chunk.index}/{total_chunks} — YOUR WRITING TASK ════════════════\n"
                f"SECTIONS: {sections_label}\n"
                f"VIDEO TITLE: \"{title}\"\n"
                f"ANCHOR / SUBJECT: {anchor}\n"
                f"LANGUAGE: {language.upper()} — every single word in {language}\n\n"
                f"STEP-BY-STEP WRITING RECIPE — execute EVERY step in order:\n"
                f"{'─' * 60}\n"
                f"{outline}\n"
                f"{'─' * 60}\n"
                f"Every sentence must execute a step from this recipe.\n"
                f"TITLE IS A CONTRACT — deliver exactly what the title promises.\n\n"
            )
        else:
            task_block = (
                f"════════════════ CHUNK {chunk.index}/{total_chunks} — YOUR WRITING TASK ════════════════\n"
                f"SECTIONS: {sections_label}\n"
                f"VIDEO TITLE: \"{title}\"\n"
                f"ANCHOR / SUBJECT: {anchor}\n"
                f"LANGUAGE: {language.upper()} — every single word in {language}\n\n"
                f"Apply your Writing Guidelines below exactly — follow the structure, tone, and rules.\n"
                f"TITLE IS A CONTRACT — deliver exactly what the title promises.\n\n"
            )

        # ── Continuation context ───────────────────────────────────────────────
        if previous_context:
            continuation = (
                f"⚠️  MID-SCRIPT — writing [{current_section_label}]. Script already in progress.\n"
                f"FORBIDDEN OPENERS: 'Bonjour' / 'Hello' / 'Today' / 'Dans cette vidéo' / "
                f"'Imagine' / 'Welcome' / 'Subscribe' — any of these = restart = forbidden.\n"
                f"CONTINUE directly after:\n"
                f'"{previous_context}"\n\n'
            )
        else:
            continuation = ""

        # ── Promo counter ──────────────────────────────────────────────────────
        if promo_count == 0:
            promo_reminder = ""
        elif chunk.index > 1:
            remaining = promo_count - promo_count_so_far
            promo_reminder = (
                f"PROMO: {promo_count_so_far}/{promo_count} done. "
                f"Place {remaining} more promo block(s) per your Writing Guidelines.\n"
                f"PRODUCT: {product}\n\n"
            ) if remaining > 0 else (
                f"PROMO: All {promo_count} done. Do NOT add more.\n\n"
            )
        else:
            promo_reminder = f"PRODUCT: {product}\n\n" if promo_count > 0 else ""

        # ── Section boundary lock (last 8 only — prevents prompt bloat) ───────
        if sections_already_done:
            recent_done = sections_already_done[-8:]
            older_count = len(sections_already_done) - len(recent_done)
            summary_line = f"   (+ {older_count} earlier sections already written)\n" if older_count else ""
            boundary_block = (
                f"⛔ DO NOT REVISIT — already written:\n"
                + summary_line
                + "".join(f"   ✓ {s}\n" for s in recent_done)
                + f"Move FORWARD only. Write what comes NEXT in the formula.\n\n"
            )
        else:
            boundary_block = ""

        # ── Final chunk stop ───────────────────────────────────────────────────
        cta_chars_approx = len(cta_action) + 20
        closing_body_chars = chunk.target_chars - cta_chars_approx

        if is_final:
            stop_instruction = (
                f"\n⛔ STOP SIGNAL: After the CTA line write exactly: {STOP_SIGNAL}\n"
                f"Write this ONLY after the CTA. Do not write it early.\n"
            )
            role_note = (
                f"FINAL CHUNK — CLOSING BODY + CTA.\n"
                f"\n"
                f"THIS CHUNK HAS {chunk.target_chars:,} CHARACTERS TO FILL.\n"
                f"  • CLOSING CONTENT: ~{closing_body_chars:,} chars of real, deep, high-value content.\n"
                f"  • CTA SECTION: only the last ~{cta_chars_approx} chars.\n"
                f"\n"
                f"CLOSING CONTENT STRUCTURE (fill in this exact order):\n"
                f"  STEP 1 — DEPTH PAYOFF: Complete the deepest insight promised by the title. Give the full mechanism.\n"
                f"  STEP 2 — OBJECTION KILL: Address the top 2-3 objections the viewer has right now. Destroy them with specifics.\n"
                f"  STEP 3 — FINAL STORY / RESULT: One concrete example, case, or result that locks everything in.\n"
                f"  STEP 4 — TRANSFORMATION MOMENT: Show the viewer who they become if they act on this. Be visceral.\n"
                f"  STEP 5 — RESIDUE LINE: One quotable sentence they will repeat to someone tomorrow.\n"
                f"  STEP 6 — CTA: '{cta_action}' — exact, verbatim, no changes.\n"
                f"\n"
                f"MANDATORY:\n"
                f"  • Do NOT jump to the CTA after step 1 or 2. The full 5 steps must be written first.\n"
                f"  • Every step gets multiple paragraphs — not one sentence.\n"
                f"  • The viewer must feel the journey is 100%% complete AND that they must act.\n"
                f"\n"
                f"FORBIDDEN: vague summaries, 'so there you have it', new topics, repeating earlier points verbatim.\n"
            )
        else:
            stop_instruction = ""
            role_note = (
                f"MID-SCRIPT chunk {chunk.index}/{total_chunks} [{current_section_label}].\n"
                f"⛔ NO intro / hook / greeting / CTA — forbidden (video already started).\n"
                f"Write {word_target} words of body content then stop (next chunk continues)."
            )

        # ── Build new quality/enforcement blocks ─────────────────────────────────
        formula_core_block = self._build_formula_core(chunk.index, total_chunks)  # Fix 2+4
        self_check_block   = self._build_self_check(chunk.index, total_chunks, is_final)  # Fix 3

        # ── Length control — in-prompt, not trimming (Fix 6) ──────────────────
        max_chars  = int(chunk.target_chars * 1.15)   # ceiling: 15% over target
        min_chars  = int(chunk.target_chars * 0.92)   # floor: never fall below 92%
        length_block = (
            f"LENGTH CONTROL — MANDATORY:\n"
            f"  Target  : {chunk.target_chars:,} characters (~{word_target} words)\n"
            f"  Minimum : {min_chars:,} characters — stopping below this is a FAILURE.\n"
            f"  Maximum : {max_chars:,} characters — stay under this.\n"
            f"  FILL every section fully. Every point needs depth, examples, specificity.\n"
            f"  DO NOT end early. DO NOT skip sections. DO NOT summarize — WRITE IN FULL.\n"
            f"  Cutting short to save effort is FORBIDDEN.\n"
        )

        # ── Prompt assembly ────────────────────────────────────────────────────
        # Order:
        #   formula_core_block @ position-0  → universal + chunk-specific quality laws (Fix 2+4)
        #   laws_block         @ position-1  → DNA priority summary of niche formula
        #   task_block         @ position-2  → specific writing recipe for this chunk
        #   continuation/boundary/promo      → context management
        #   formula_block      @ body        → full raw Writing Guidelines (Fix 1)
        #   role + length                    → position note + tight length target (Fix 6)
        #   self_check_block   @ end         → quality gate before output (Fix 3)
        prompt = (
            f"{formula_core_block}"
            f"{laws_block}"
            f"{task_block}"
            f"{continuation}"
            f"{boundary_block}"
            f"{promo_reminder}"
            f"{formula_block}"
            f"ROLE: {role_note}\n"
            f"{length_block}"
            f"{self_check_block}"
            f"{stop_instruction}\n"
            f"WRITE NOW:"
        )

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
        MAX_SHORT_RETRIES = 3

        active_prompt = prompt
        last_text     = ""

        for short_attempt in range(MAX_SHORT_RETRIES + 1):
            for attempt in range(MAX_API_RETRIES + 1):
                try:
                    model = genai.GenerativeModel(
                        model_name,
                        system_instruction=system_instruction,
                    )
                    response = model.generate_content(
                        active_prompt,
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
            min_ok  = int(target_chars * 0.85)
            if len(text) >= min_ok or short_attempt == MAX_SHORT_RETRIES:
                # If we have a continuation, prepend the earlier output
                return (last_text + "\n\n" + text).strip() if last_text else text

            if verbose:
                print(f"   ⚠️  {label} too short ({len(text):,} < {min_ok:,}) "
                      f"— retrying (attempt {short_attempt + 1}/{MAX_SHORT_RETRIES})...")

            # Build continuation prompt: show what was written, demand more
            still_need = target_chars - len(text)
            last_text  = (last_text + "\n\n" + text).strip() if last_text else text
            active_prompt = (
                f"⚠️  LENGTH FAILURE — CONTINUATION REQUIRED ⚠️\n\n"
                f"You wrote {len(last_text):,} characters but the target is {target_chars:,}.\n"
                f"You MUST write at least {still_need:,} MORE characters of high-quality content.\n\n"
                f"RULES:\n"
                f"• Continue DIRECTLY from the last line below — do NOT restart, do NOT repeat.\n"
                f"• Add depth, examples, specifics, elaboration — not padding.\n"
                f"• Follow the formula exactly. Every sentence must earn its place.\n"
                f"• Do NOT include greetings, meta-comments, or explanations.\n\n"
                f"--- CONTINUE FROM HERE ---\n"
                f"{last_text[-600:]}\n"
                f"--- WRITE {still_need:,}+ MORE CHARACTERS NOW ---\n"
            )
            time.sleep(2)

        return last_text

    # =========================================================================
    # CLAUDE API CALL — proxy at api.gngn.my (same prompt structure as Gemini)
    # =========================================================================

    def _call_api_claude(
        self,
        prompt: str,
        system_instruction: str,
        target_chars: int,
        label: str = "",
        verbose: bool = False,
    ) -> str:
        """Call Claude claude-sonnet-4-6 via the custom proxy using plain requests."""
        import requests as _requests

        CLAUDE_ENDPOINT = "https://api.gngn.my/v1/messages"
        CLAUDE_MODEL    = "claude-sonnet-4-6"
        MAX_TOKENS      = 16000
        MAX_SHORT_RETRIES = 3

        api_key = Config.get_claude_api_key()
        if not api_key:
            raise RuntimeError("Claude API key not configured. Add it in Settings → Claude API.")

        headers = {
            "Content-Type" : "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        active_prompt = prompt
        last_text     = ""

        for short_attempt in range(MAX_SHORT_RETRIES + 1):
            body = {
                "model"     : CLAUDE_MODEL,
                "max_tokens": MAX_TOKENS,
                "system"    : system_instruction,
                "messages"  : [{"role": "user", "content": active_prompt}],
            }

            for attempt in range(4):
                try:
                    resp = _requests.post(
                        CLAUDE_ENDPOINT, headers=headers, json=body, timeout=600
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    text = (data.get("content", [{}])[0].get("text") or "").strip()
                    break
                except Exception as exc:
                    err = str(exc)
                    is_rate = "429" in err or "overloaded" in err.lower() or "rate" in err.lower()
                    if not is_rate or attempt == 3:
                        raise
                    wait = 30 * (attempt + 1)
                    if verbose:
                        print(f"   ⚠️  Claude rate limit — waiting {wait}s (attempt {attempt+1}/3)...")
                    time.sleep(wait)

            min_ok = int(target_chars * 0.85)
            if len(text) >= min_ok or short_attempt == MAX_SHORT_RETRIES:
                return (last_text + "\n\n" + text).strip() if last_text else text

            if verbose:
                print(f"   ⚠️  {label} too short ({len(text):,} < {min_ok:,}) "
                      f"— Claude retry {short_attempt + 1}/{MAX_SHORT_RETRIES}...")

            still_need = target_chars - len(text)
            last_text  = (last_text + "\n\n" + text).strip() if last_text else text
            active_prompt = (
                f"⚠️  LENGTH FAILURE — CONTINUATION REQUIRED ⚠️\n\n"
                f"You wrote {len(last_text):,} characters but the target is {target_chars:,}.\n"
                f"Write at least {still_need:,} MORE characters of high-quality content.\n\n"
                f"Continue DIRECTLY from the last line below — do NOT restart, do NOT repeat:\n"
                f"--- CONTINUE FROM HERE ---\n"
                f"{last_text[-600:]}\n"
                f"--- WRITE {still_need:,}+ MORE CHARACTERS NOW ---\n"
            )
            time.sleep(2)

        return last_text

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
        sections_done: List[str] = None,
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
        done_list   = sections_done or []

        # Find sections not yet written — prefer extending those
        remaining_secs = [s for s in body_secs if s not in done_list]
        mid_secs = remaining_secs[:-1] if len(remaining_secs) > 1 else remaining_secs
        body_hint = (
            "Continue these REMAINING body sections from the Writing Guidelines: " + ", ".join(mid_secs)
        ) if mid_secs else "Continue the body / development sections prescribed by your Writing Guidelines."

        # Build forbidden block for extension prompts
        if done_list:
            forbidden_ext = (
                f"\n⛔ ALREADY WRITTEN — DO NOT REVISIT, DO NOT REPEAT, DO NOT REOPEN:\n"
                + "".join(f"  ✓ {s}\n" for s in done_list)
                + f"\nEvery sentence must move FORWARD in the formula. Backward = forbidden.\n"
            )
        else:
            forbidden_ext = ""

        system_instruction = self._build_system_instruction(language)

        for attempt in range(MAX_RETRIES):
            shortage = target_length - len(current_script)
            if shortage <= 0:
                break

            # Request the exact shortage + a small buffer so one call can close it
            extend_chars  = shortage + 2000
            extend_tokens = min(65536, max(int(extend_chars / 3 * 1.3) + 3000, 6000))
            tail          = current_script[-800:].strip()

            # Use DNA when available — avoids re-injecting the full 70K formula
            # into every extension call (10x smaller prompt = significantly faster response)
            formula_dna = plan.get("formula_dna", "") if plan else ""
            use_dna = len(formula_dna) >= _DNA_MIN_CHARS

            if use_dna:
                formula_block = (
                    f"══════════ NICHE FORMULA DNA (ALL LAWS) ══════════\n"
                    f"{formula_dna}\n"
                    f"══════════════════════════════════════════════════\n"
                )
            else:
                formula_block = (
                    f"══════════ WRITING GUIDELINES (execute ALL rules) ══════════\n"
                    f"{formula}\n"
                    f"════════════════════════════════════════════════════════════\n"
                )

            prompt = f"""{formula_block}
{forbidden_ext}
⚠️  SCRIPT EXTENSION — YOU ARE CONTINUING A SCRIPT ALREADY IN PROGRESS.
DO NOT start a new intro. DO NOT write a new hook. DO NOT say 'Bonjour' or 'Hello' or any greeting.
DO NOT write 'Subscribe', 'Abonnez-vous', or any CTA — the script is not finished yet.
DO NOT repeat ideas already covered above. Every sentence must add NEW information.
The script is mid-way through. You MUST continue from the last sentence below.

TITLE: "{title}"
TITLE IS A CONTRACT — stay locked to the exact promise in the title.
SUBJECT: {anchor}

THE SCRIPT ENDED HERE — CONTINUE FROM THIS EXACT POINT:
"{tail}"

TASK: {body_hint}
Write at least {extend_chars:,} characters. Apply the formula tone, style, structure.

WRITE IN {language.upper()} — CONTINUE NOW:"""

            # Flash is fast enough for extensions — formula is explicit via DNA
            ext_model = Config.GEMINI_PLAN_MODEL if use_dna else Config.GEMINI_SCRIPT_MODEL

            try:
                extension = self._call_api(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    model_name=ext_model,
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
                time.sleep(2)
            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Extension {attempt + 1} failed: {e}")
                break

        return current_script

    # =========================================================================
    # POST-PROCESSING
    # =========================================================================

    def _merge_chunks(self, chunks: List[str]) -> str:
        # Join with double newline so restart-detection patterns are preserved
        merged = "\n\n".join(c.strip() for c in chunks if c.strip())
        merged = re.sub(r"(?i)(continuing from|as we discussed|as mentioned earlier)", "", merged)
        merged = re.sub(r"(?i)(in the previous (section|part|chunk))", "", merged)
        merged = re.sub(r"\n{3,}", "\n\n", merged)
        merged = re.sub(r"  +", " ", merged)
        return merged.strip()

    # Opening/intro sentence patterns that signal a restart (multi-language)
    _RESTART_PATTERNS = [
        r"(?:^|\n\n|\. |\! |\? )"
        r"(aujourd'?hui|today|dans cette vid[eé]o|in this video|"
        r"bienvenue|bonjour|hello|welcome back|salut|"
        r"dans cette nouvelle|in today's video|"
        r"nous allons (voir|d[eé]couvrir|parler|explorer)|"
        r"we('re| are) going to|i'm going to (show|tell|reveal)|"
        r"let me (tell|show|introduce)|picture this:|imagine)",
    ]

    def _cut_at_restart(self, text: str, cta_action: str, verbose: bool = False) -> str:
        """
        Cut everything after the last real ending of the script.

        Strategy (in priority order):
        1. STOP_SIGNAL → already handled in _clean_script (safety net here too).
        2. Find the LAST CTA phrase. If >50 chars follow it → cut right after the
           CTA sentence.  The old ≥3% gate is REMOVED — even a 100-char restart
           after the CTA must be dropped.
        3. Restart-sentence detection: after the last CTA, look for opening/greeting
           patterns that signal the model started a new script section.  Cut there.
        """
        # CTA trigger phrases (multi-language)
        cta_patterns = [
            r'\b(abonnez[\s\-]vous|subscribe|abonne[\s\-]toi|s\'abonner)\b',
            r'\b(clique\s+sur\s+la\s+cloche|hit\s+the\s+bell|ring\s+the\s+bell)\b',
            r'\b(like\s+et\s+commente|like\s+and\s+comment)\b',
            r'\b(active\s+les\s+notifications|turn\s+on\s+notifications)\b',
            r'\b(partage\s+(cette|la)\s+vid[eé]o|share\s+this\s+video)\b',
            r'\b(à\s+la\s+prochaine|see\s+you\s+(next|in\s+the\s+next))\b',
        ]
        if cta_action and len(cta_action) > 8:
            cta_patterns.append(re.escape(cta_action[:40].lower()))

        text_lower = text.lower()

        # ── Step 1: Find the LAST CTA sentence boundary ───────────────────────
        last_cut_pos = -1

        for pat in cta_patterns:
            for m in re.finditer(pat, text_lower):
                sentence_end = re.search(r'[.!?]', text[m.end():])
                cut_candidate = m.end() + (sentence_end.end() if sentence_end else 0)
                after_content = text[cut_candidate:].strip()
                # Cut if ANY meaningful content follows (lowered from 150 → 50)
                if len(after_content) > 50:
                    if cut_candidate > last_cut_pos:
                        last_cut_pos = cut_candidate

        if last_cut_pos > 0:
            if verbose:
                chars_cut = len(text) - last_cut_pos
                print(f"   ✂️  CTA-cut: removed {chars_cut:,} chars after last CTA "
                      f"(pos {last_cut_pos:,}/{len(text):,})")
            return text[:last_cut_pos].strip()

        # ── Step 2: Restart-sentence detection (no CTA found above) ───────────
        # Look for intro/greeting sentences anywhere past the 60% mark of the text
        # (before that they're legitimate in some formulas).
        search_start = int(len(text) * 0.60)
        tail         = text_lower[search_start:]

        for pat in self._RESTART_PATTERNS:
            m = re.search(pat, tail, re.IGNORECASE)
            if m:
                # Absolute position in full text
                abs_pos = search_start + m.start()
                # Move to the start of the sentence (after the delimiter)
                # Skip leading newlines/spaces
                while abs_pos < len(text) and text[abs_pos] in ('\n', ' ', '.', '!', '?'):
                    abs_pos += 1
                after_content = text[abs_pos:].strip()
                if len(after_content) > 80:
                    if verbose:
                        print(f"   ✂️  Restart-cut: detected new intro at pos {abs_pos:,} "
                              f"({len(after_content):,} chars removed)")
                    return text[:abs_pos].strip()

        return text

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

    # Stopwords to strip before similarity comparison (French + English)
    _STOPWORDS = {
        "le","la","les","de","du","des","un","une","et","est","en","au","aux",
        "que","qui","par","sur","dans","avec","pour","pas","plus","mais","ou",
        "donc","or","ni","car","si","ce","se","il","elle","ils","elles","on",
        "nous","vous","je","tu","me","te","lui","leur","y","a","être","avoir",
        "the","a","an","and","or","but","in","on","at","to","of","for","with",
        "is","are","was","were","be","been","have","has","had","do","does","did",
        "this","that","these","those","it","its","we","you","he","she","they",
        "not","no","so","if","as","by","from","up","about","than","into",
    }

    def _sentence_key(self, sent: str) -> frozenset:
        """Return a frozenset of meaningful words (stopwords removed)."""
        words = re.sub(r"[^\w\s]", "", sent.lower()).split()
        return frozenset(w for w in words if w not in self._STOPWORDS and len(w) > 2)

    def _jaccard(self, a: frozenset, b: frozenset) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _remove_duplicate_sentences(self, text: str, verbose: bool = False) -> str:
        """
        Remove duplicate AND near-duplicate sentences.
        Two sentences are considered duplicates if:
          - They are identical after normalisation (exact), OR
          - Their Jaccard similarity on meaningful words is ≥ 0.72
            (catches the same idea paraphrased with slightly different words)
        Short sentences (<40 chars) are always kept — they are transitions,
        not padding.
        """
        SIMILARITY_THRESHOLD = 0.72

        sentences = re.split(r"(?<=[.!?])\s+", text)
        kept_keys: List[frozenset] = []
        unique: List[str] = []
        removed = 0

        for sent in sentences:
            norm = re.sub(r"\s+", " ", sent).strip()
            if len(norm) < 40:
                unique.append(sent)
                continue

            key = self._sentence_key(norm)
            if not key:
                unique.append(sent)
                continue

            # Check against every kept sentence
            is_dup = False
            for kept in kept_keys:
                if self._jaccard(key, kept) >= SIMILARITY_THRESHOLD:
                    is_dup = True
                    break

            if is_dup:
                removed += 1
            else:
                kept_keys.append(key)
                unique.append(sent)

        if verbose and removed:
            print(f"   🧹 Semantic dedup: removed {removed} near-duplicate sentence(s)")

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

#!/usr/bin/env python3
"""
Formula Extractor — Deep analysis of long scripts to extract reusable writing formulas.

Input : a long script (up to 250,000 chars) + name + language
Output: a 30K+ char "Writing Guidelines" formula stored as a Niche the user can
        select in the Script Writer.

Pipeline
--------
1. If script is very long, split into sections of ~80K chars (token-safe).
2. PASS A — Per-chunk analysis: Gemini extracts raw patterns from each chunk
   (hooks, rhythm, transitions, vocabulary, retention devices, escalation…).
3. PASS B — Synthesis: feed every per-chunk pattern dump back to Gemini; it
   merges them into ONE definitive formula structured so the Script Writer
   can inject it as `writing_guidelines`.
4. PASS C — Expansion (only if formula < 30K chars): Gemini expands every
   section with concrete examples, additional laws, anti-patterns, and style
   lock rules until the target length is reached.
"""

from __future__ import annotations

import time
from typing import List, Optional

import google.generativeai as genai
from config import Config

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_NAME          = "gemini-2.5-pro"
MAX_SCRIPT_CHARS    = 250_000
MAX_CHUNK_CHARS     = 80_000
TARGET_FORMULA_CHARS = 30_000
MAX_EXPANSION_PASSES = 3


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
_ANALYSIS_PROMPT = """You are a world-class script analyst. Your job is to reverse-engineer the exact
writing formula used in the script below.

Extract EVERY observable pattern — no guessing, no vague statements. Anchor every
observation with a short quote from the script that proves the pattern exists.

Language of the script: {language}

=== SCRIPT CHUNK {index}/{total} ===
{chunk}
=== END CHUNK ===

Return a detailed technical report with these sections (no limits on length — be
exhaustive, include direct quotes):

1. HOOK & OPENING PATTERNS
   - How does the writer open? Tension device? Question? Bold claim? List every hook type used with quotes.

2. SENTENCE RHYTHM & CADENCE
   - Average sentence length. Short/long pattern. Punchlines. Staccato vs flowing.

3. VOICE, TONE & PERSONA
   - Who is speaking? Confidence level? Emotional register? Authority markers?

4. VOCABULARY & PHRASING SIGNATURES
   - Pet words, repeated constructions, metaphor types, analogy style.
   - List the 30 most distinctive words or phrases with exact quotes.

5. PARAGRAPH / SECTION STRUCTURE
   - How does the writer chain ideas? Topic → payload → echo? Claim → proof → payoff?

6. TRANSITIONS & CONNECTORS
   - Exact transition words / bridging sentences used between ideas. List them.

7. RETENTION TECHNIQUES
   - Open loops, cliffhangers, "but first…" delays, promises, teases, callbacks.
   - Quote every instance.

8. ESCALATION & TENSION BUILDING
   - How does stakes/intensity grow across the chunk?

9. EVIDENCE & SPECIFICITY
   - Numbers, names, dates, examples, case studies — density + style.

10. EMOTIONAL TRIGGERS
    - Fear, curiosity, aspiration, anger, shame, hope — which beats use which?

11. CLOSING & CTA PATTERNS
    - If this chunk contains endings/CTAs/bypasses, analyse them.

12. FORBIDDEN / NEVER-USED PATTERNS
    - What does the writer AVOID? (filler words, hedges, clichés, generic AI phrasing, etc.)

13. ANY OTHER DISTINCTIVE SIGNATURES
    - Anything that makes this script unmistakably itself.

Be relentless. Quote the script. Output RAW PATTERNS ONLY — do not write a formula yet.
"""


_SYNTHESIS_PROMPT = """You are building the definitive "Writing Guidelines" document for a Script Writer AI.

Below are {n_dumps} technical pattern reports extracted from different chunks of the
SAME script. Your job is to merge them into ONE complete, reusable FORMULA that any
writer can apply to create new scripts with IDENTICAL style and structure.

Target language for the resulting formula: {language}
Niche name: {name}

=== RAW PATTERN DUMPS ===
{dumps}
=== END DUMPS ===

OUTPUT REQUIREMENTS
• Minimum length: {target_chars:,} characters of actionable instructions.
• Tone: strict, imperative, prescriptive ("DO / NEVER / ALWAYS / EXAMPLE").
• Every rule must be concrete with a SHORT example taken from the source material
  (or a clean paraphrase). NO vague advice.
• Structure the formula like a professional writing manual.

MANDATORY SECTIONS (in this exact order, each with real depth):

═══════════════════════════════════════════════════════════
FORMULA: {name}
═══════════════════════════════════════════════════════════

SECTION 1 — CORE IDENTITY & VOICE
  • Who is the narrator
  • Emotional register, confidence level
  • Persona anchors (traits the voice must never lose)

SECTION 2 — UNIVERSAL LAWS (MANDATORY FOR EVERY SENTENCE)
  • At least 15 numbered laws
  • Each law: RULE → WHY → EXAMPLE → ANTI-EXAMPLE

SECTION 3 — HOOK MECHANICS (OPENING)
  • All observed hook archetypes
  • Opening-sentence templates (fill-in-the-blank)
  • Forbidden openings

SECTION 4 — SENTENCE & CADENCE RULES
  • Length ranges, rhythm patterns
  • Punchline placement
  • Staccato vs flowing trigger conditions

SECTION 5 — PARAGRAPH / BEAT STRUCTURE
  • How a beat is built (claim → proof → payoff → teaser, etc.)
  • Ideal beat length
  • Beat-to-beat chaining rules

SECTION 6 — TRANSITIONS & CONNECTORS
  • Exhaustive list of allowed bridges
  • Forbidden transitions

SECTION 7 — VOCABULARY & SIGNATURE PHRASES
  • Approved vocabulary bank (~60 items) — words the writer SHOULD reach for
  • Signature constructions (templates) with examples
  • Forbidden words & phrases (all generic-AI sludge)

SECTION 8 — RETENTION & OPEN-LOOP SYSTEM
  • Every retention device with trigger conditions
  • How to place open loops, callbacks, teases
  • Density rules (how often)

SECTION 9 — ESCALATION CURVE
  • How intensity/tension rises across a script
  • Milestones: opening → early-mid → late-mid → closing

SECTION 10 — EVIDENCE & SPECIFICITY RULES
  • Required density of numbers, names, dates
  • How to insert evidence without slowing the pace

SECTION 11 — EMOTIONAL TRIGGER PLAYBOOK
  • Which emotion for which beat
  • Language presets for each emotion

SECTION 12 — CLOSING & BYPASS PATTERNS
  • Objection-killers
  • CTA templates
  • Final-line archetypes

SECTION 13 — STYLE LOCK (ANTI-GENERIC FIREWALL)
  • What would sound like a generic AI — and never appears here
  • What would sound like a bland YouTube voice — and never appears here
  • Specific words/phrases that are banned ON SIGHT

SECTION 14 — CHUNK-POSITION RULES
  • Opening chunk rules
  • Early-middle chunk rules
  • Late-middle chunk rules
  • Closing chunk rules

SECTION 15 — QUALITY CHECKLIST (SELF-CHECK BEFORE OUTPUT)
  • 12+ yes/no questions the writer must pass before releasing the script

NOW: produce the full formula. Be exhaustive. Quote where useful. Do NOT
summarize. Hit the {target_chars:,}-character target. Begin:
"""


_EXPANSION_PROMPT = """Your formula below is only {current_chars:,} characters. We need at least
{target_chars:,} characters of ACTIONABLE content. Do NOT pad with filler.

Expand every thin section with:
  • More concrete examples drawn from the source style
  • More numbered laws (each with RULE → WHY → EXAMPLE → ANTI-EXAMPLE)
  • More entries in the vocabulary bank
  • More transition phrases, more hook templates
  • More forbidden-list items

Preserve the existing structure and all already-written content. Only ADD.

=== CURRENT FORMULA ===
{current}
=== END ===

Output the ENTIRE expanded formula (do not truncate). Target: {target_chars:,}+ characters.
"""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------
class FormulaExtractor:
    """Deep-analyse a long script and return a 30K+ char writing formula."""

    def __init__(self) -> None:
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise RuntimeError("Gemini API key not configured")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(MODEL_NAME)

    # ----- public --------------------------------------------------------
    def extract(
        self,
        script: str,
        name: str,
        language: str = "English",
        progress_cb=None,
    ) -> str:
        """
        Extract a full 30K+ char formula from the given script.
        progress_cb(pct:int, msg:str) is called at each milestone.
        """
        script = (script or "").strip()
        if len(script) < 500:
            raise ValueError("Script too short to extract a formula (min 500 chars).")
        if len(script) > MAX_SCRIPT_CHARS:
            raise ValueError(
                f"Script too long: {len(script):,} chars (max {MAX_SCRIPT_CHARS:,})."
            )

        def report(pct, msg):
            if progress_cb:
                progress_cb(pct, msg)
            print(f"[formula-extract] {pct}% — {msg}")

        # ── PASS A ── per-chunk raw analysis
        chunks = self._split(script)
        report(5, f"Analyzing {len(chunks)} chunk(s)…")

        pattern_dumps: List[str] = []
        for i, chunk in enumerate(chunks, start=1):
            report(
                5 + int(40 * (i - 1) / max(1, len(chunks))),
                f"Deep analysis pass {i}/{len(chunks)}…",
            )
            dump = self._run(
                _ANALYSIS_PROMPT.format(
                    chunk=chunk, index=i, total=len(chunks), language=language
                )
            )
            pattern_dumps.append(dump)

        # ── PASS B ── synthesis into single formula
        report(55, "Synthesising unified formula…")
        merged = "\n\n".join(
            f"--- CHUNK {i + 1} ---\n{d}" for i, d in enumerate(pattern_dumps)
        )
        formula = self._run(
            _SYNTHESIS_PROMPT.format(
                dumps=merged,
                n_dumps=len(pattern_dumps),
                language=language,
                name=name,
                target_chars=TARGET_FORMULA_CHARS,
            )
        )

        # ── PASS C ── expand until target length reached
        passes = 0
        while len(formula) < TARGET_FORMULA_CHARS and passes < MAX_EXPANSION_PASSES:
            passes += 1
            report(
                70 + passes * 8,
                f"Expanding formula ({len(formula):,} → {TARGET_FORMULA_CHARS:,} chars)…",
            )
            formula = self._run(
                _EXPANSION_PROMPT.format(
                    current=formula,
                    current_chars=len(formula),
                    target_chars=TARGET_FORMULA_CHARS,
                )
            )

        report(100, f"Formula ready ({len(formula):,} chars).")
        return formula

    # ----- helpers -------------------------------------------------------
    def _split(self, text: str) -> List[str]:
        """Split on paragraph boundaries, each chunk ≤ MAX_CHUNK_CHARS."""
        if len(text) <= MAX_CHUNK_CHARS:
            return [text]
        paragraphs = text.split("\n\n")
        chunks: List[str] = []
        current = ""
        for p in paragraphs:
            if len(current) + len(p) + 2 <= MAX_CHUNK_CHARS:
                current = f"{current}\n\n{p}" if current else p
            else:
                if current:
                    chunks.append(current)
                current = p
        if current:
            chunks.append(current)
        return chunks

    def _run(self, prompt: str, retries: int = 3) -> str:
        """Call Gemini with retries on transient errors."""
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                resp = self._model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.35,
                        "top_p": 0.95,
                        "max_output_tokens": 65_000,
                    },
                )
                text = (resp.text or "").strip()
                if len(text) < 200:
                    raise RuntimeError(f"Gemini returned suspiciously short output ({len(text)} chars)")
                return text
            except Exception as exc:  # pylint: disable=broad-except
                last_err = exc
                wait = min(8, 2 * attempt)
                print(f"[formula-extract] Gemini error (attempt {attempt}/{retries}): {exc} — retry in {wait}s")
                time.sleep(wait)
        raise RuntimeError(f"Gemini failed after {retries} attempts: {last_err}")

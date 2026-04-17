#!/usr/bin/env python3
"""
Ebook Generator — Chunk-Based Architecture (mirrors ScriptGenerator3Chunk)

Workflow:
  PHASE 1 — RESEARCH & OUTLINE (1 Gemini call):
    Deep research on the topic. Build a full chapter outline with key
    facts, data points, and structural plan per chapter.

  PHASE 2 — WRITE CHAPTERS (1 call per chapter):
    Each chapter gets: research context + chapter brief + previous chapter
    summary. Chunk system prevents token limit issues on large ebooks.

  PHASE 3 — BUILD PDF:
    Assemble all chapters into a clean, professional PDF using fpdf2.
"""

import re
import time
import json
from pathlib import Path
from typing import Dict, List, Optional

import google.generativeai as genai
from config import Config

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
RESEARCH_MODEL = "gemini-2.5-pro-preview-06-05"
WRITE_MODEL    = "gemini-2.5-pro-preview-06-05"

# Words per PDF page (standard ebook density)
WORDS_PER_PAGE = 350

# Gemini output token cap per chapter call
MAX_TOKENS_PER_CHAPTER = 65536


class EbookGenerator:

    def __init__(self):
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)

    # =========================================================================
    # PUBLIC
    # =========================================================================

    def generate(
        self,
        title: str,
        details: str,
        pages: int,
        verbose: bool = True,
    ) -> Dict:
        start = time.time()

        pages   = max(5, min(pages, 500))
        n_chaps = self._chapter_count(pages)
        words_target = pages * WORDS_PER_PAGE

        if verbose:
            print(f"\n{'='*65}")
            print(f"📚 EBOOK GENERATION — CHUNK ARCHITECTURE")
            print(f"{'='*65}")
            print(f"Title    : {title}")
            print(f"Pages    : {pages}  (~{words_target:,} words)")
            print(f"Chapters : {n_chaps}")
            print(f"Model    : {WRITE_MODEL}")
            print(f"{'='*65}\n")

        # ── Phase 1: Research & Outline ────────────────────────────────────
        if verbose:
            print("🔍 PHASE 1 — Research & outline…")
        outline = self._research_and_outline(title, details, pages, n_chaps, verbose)
        if verbose:
            print(f"   ✅ {len(outline['chapters'])} chapters planned\n")

        # ── Phase 2: Write each chapter ───────────────────────────────────
        if verbose:
            print("✍️  PHASE 2 — Writing chapters…")
        chapters: List[Dict] = []
        prev_summary = ""
        words_per_chapter = words_target // n_chaps

        for i, chap_plan in enumerate(outline["chapters"], 1):
            if verbose:
                print(f"   Chapter {i}/{n_chaps}: {chap_plan['title']} (~{words_per_chapter} words)…")
            text = self._write_chapter(
                ebook_title=title,
                details=details,
                research=outline["research"],
                chapter_plan=chap_plan,
                chapter_index=i,
                total_chapters=n_chaps,
                words_target=words_per_chapter,
                previous_summary=prev_summary,
                verbose=verbose,
            )
            chapters.append({"title": chap_plan["title"], "content": text})
            prev_summary = self._summarize(text)
            if i < n_chaps:
                time.sleep(0.5)

        # ── Phase 3: Build PDF ─────────────────────────────────────────────
        if verbose:
            print("\n📄 PHASE 3 — Building PDF…")
        output_dir = Path("output/ebooks")
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"{self._safe_filename(title)}.pdf"

        from pdf_builder import EbookPDFBuilder
        builder = EbookPDFBuilder()
        builder.build(
            title=title,
            subtitle=details[:120] if len(details) > 120 else details,
            chapters=chapters,
            output_path=pdf_path,
        )

        total_words = sum(len(c["content"].split()) for c in chapters)
        elapsed = time.time() - start

        if verbose:
            print(f"\n{'='*65}")
            print(f"✅ EBOOK COMPLETE")
            print(f"   File    : {pdf_path}")
            print(f"   Words   : {total_words:,}")
            print(f"   Chapters: {len(chapters)}")
            print(f"   Time    : {elapsed:.1f}s")
            print(f"{'='*65}\n")

        return {
            "success"     : True,
            "pdf_path"    : str(pdf_path),
            "filename"    : pdf_path.name,
            "chapters"    : len(chapters),
            "total_words" : total_words,
            "elapsed"     : round(elapsed, 1),
        }

    # =========================================================================
    # PHASE 1 — RESEARCH & OUTLINE
    # =========================================================================

    def _research_and_outline(
        self,
        title: str,
        details: str,
        pages: int,
        n_chaps: int,
        verbose: bool,
    ) -> Dict:
        prompt = f"""You are an expert researcher and ebook planner.

EBOOK TITLE: "{title}"
USER REQUEST: {details}
TARGET: {pages} pages (~{pages * WORDS_PER_PAGE:,} words), {n_chaps} chapters

YOUR JOB — TWO PARTS:

PART A — DEEP RESEARCH:
Do a comprehensive research brief on this topic. Include:
- Key facts, statistics, data points
- Common problems/solutions (if applicable)
- Expert insights and best practices
- Real-world examples and case studies
- Most important things the reader must know
Write this as a detailed research summary (minimum 800 words).

PART B — CHAPTER OUTLINE:
Create exactly {n_chaps} chapters. For each chapter provide:
- Chapter title (specific, compelling)
- 3-5 key points to cover
- Specific facts/examples to include from your research
- Target angle (educational, practical, analytical, etc.)

OUTPUT FORMAT — use this exact XML:

<research>
[Your detailed research summary here — minimum 800 words]
</research>

<chapters>
<chapter>
<number>1</number>
<title>[Chapter title]</title>
<key_points>[Point 1 | Point 2 | Point 3 | ...]</key_points>
<content_brief>[What to write — specific, actionable]</content_brief>
<facts>[Key facts/stats/examples to include]</facts>
</chapter>
[repeat for all {n_chaps} chapters]
</chapters>

Rules:
- Research must be factual, specific, and deep — no generic filler
- Chapter titles must be compelling and specific, not generic
- Each chapter must have a clear purpose and angle
- All {n_chaps} chapter tags must be present"""

        if verbose:
            print(f"   📤 Research call ({len(prompt):,} chars)…")
        try:
            model    = genai.GenerativeModel(RESEARCH_MODEL)
            response = model.generate_content(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 65536},
            )
            text = response.text.strip()
            if verbose:
                print(f"   📥 Response: {len(text):,} chars")
        except Exception as e:
            if verbose:
                print(f"   ⚠️  Research call failed ({e}) — using minimal fallback")
            return self._fallback_outline(title, details, n_chaps)

        return self._parse_outline(text, title, n_chaps)

    def _parse_outline(self, text: str, title: str, n_chaps: int) -> Dict:
        def _xml(tag: str, src: str, fallback: str = "") -> str:
            m = re.search(rf'<{tag}>(.*?)</{tag}>', src, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else fallback

        research = _xml("research", text, f"Research on {title}")

        chapters = []
        chap_matches = re.findall(r'<chapter>(.*?)</chapter>', text, re.DOTALL | re.IGNORECASE)
        for i, cm in enumerate(chap_matches[:n_chaps], 1):
            chap_title  = _xml("title", cm, f"Chapter {i}")
            key_points  = _xml("key_points", cm, "")
            brief       = _xml("content_brief", cm, "")
            facts       = _xml("facts", cm, "")
            chapters.append({
                "number"    : i,
                "title"     : chap_title,
                "key_points": [p.strip() for p in key_points.split("|") if p.strip()],
                "brief"     : brief,
                "facts"     : facts,
            })

        # Pad if parsing missed some chapters
        while len(chapters) < n_chaps:
            i = len(chapters) + 1
            chapters.append({
                "number": i, "title": f"Chapter {i}",
                "key_points": [], "brief": "", "facts": "",
            })

        return {"research": research, "chapters": chapters}

    def _fallback_outline(self, title: str, details: str, n_chaps: int) -> Dict:
        chapters = [
            {"number": i, "title": f"Chapter {i}: {title}",
             "key_points": [], "brief": details, "facts": ""}
            for i in range(1, n_chaps + 1)
        ]
        return {"research": details, "chapters": chapters}

    # =========================================================================
    # PHASE 2 — WRITE CHAPTER
    # =========================================================================

    def _write_chapter(
        self,
        ebook_title: str,
        details: str,
        research: str,
        chapter_plan: Dict,
        chapter_index: int,
        total_chapters: int,
        words_target: int,
        previous_summary: str,
        verbose: bool,
    ) -> str:
        chap_title  = chapter_plan["title"]
        key_points  = " | ".join(chapter_plan.get("key_points", [])) or "Cover topic thoroughly"
        brief       = chapter_plan.get("brief", "")
        facts       = chapter_plan.get("facts", "")

        is_first = chapter_index == 1
        is_last  = chapter_index == total_chapters

        position_note = (
            "OPENING CHAPTER: hook the reader immediately, set the stage, establish why this matters."
            if is_first else
            "FINAL CHAPTER: deliver the climax, practical takeaways, strong memorable close."
            if is_last else
            f"MID CHAPTER {chapter_index}/{total_chapters}: deepen the topic, add proof and examples, escalate value."
        )

        continuation = (
            f"\nPREVIOUS CHAPTER SUMMARY (continue naturally, do NOT repeat):\n{previous_summary}\n"
            if previous_summary else ""
        )

        prompt = f"""You are an expert ebook writer. Write one complete chapter with exceptional quality.

═══════════════════ EBOOK CONTEXT ═══════════════════
EBOOK TITLE: "{ebook_title}"
TOPIC/PURPOSE: {details}

═══════════════════ RESEARCH BASE ═══════════════════
{research[:3000]}
[...full research available above]

═══════════════════ YOUR CHAPTER ═══════════════════
CHAPTER {chapter_index}/{total_chapters}: {chap_title}
KEY POINTS TO COVER: {key_points}
CONTENT BRIEF: {brief}
FACTS/EXAMPLES TO USE: {facts}
{continuation}
═══════════════════ WRITING LAWS ═══════════════════
QUALITY RULES (mandatory for every paragraph):
  ✓ START STRONG: First sentence must grab — no warmup, no "In this chapter we will..."
  ✓ SPECIFICITY: Every claim backed by fact, number, example, or case study
  ✓ VALUE DENSITY: Every paragraph teaches something concrete and actionable
  ✓ NO FILLER: Zero padding sentences. Every sentence earns its place.
  ✓ ESCALATION: Each section goes deeper than the last
  ✓ READABLE: Short punchy paragraphs (3-5 sentences). Vary sentence length.
  ✓ EXPERT VOICE: Write like someone who knows this topic deeply — not like a textbook

STYLE: Direct, authoritative, practical. Like a knowledgeable mentor sharing real insights.
FORBIDDEN: "In this chapter", "As we discussed", "It is important to note", generic filler phrases

POSITION: {position_note}

═══════════════════ SELF-CHECK BEFORE OUTPUT ═══════════════════
Before writing, verify:
  ✓ Does the first sentence hook the reader?
  ✓ Is every claim supported by a specific fact or example?
  ✓ Is each paragraph adding new value (no repetition)?
  ✓ Is the writing specific and expert-level, not generic?
  ✓ Does the chapter have a strong opening AND strong closing paragraph?

═══════════════════ LENGTH ═══════════════════
TARGET: {words_target} words (minimum {int(words_target * 0.9)}, maximum {int(words_target * 1.1)})
Write the complete chapter text. Start directly with the chapter content.
Do NOT write chapter titles or headers in the text — those are added by the PDF builder.

WRITE THE CHAPTER NOW:"""

        max_tokens = min(65536, max(int(words_target / 0.75) + 2000, 4000))

        for attempt in range(3):
            try:
                model = genai.GenerativeModel(WRITE_MODEL)
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature"      : 0.75,
                        "max_output_tokens": max_tokens,
                        "top_p"            : 0.95,
                    },
                )
                text = response.text.strip()
                if len(text) >= int(words_target * 0.5 * 4.5):  # ~chars check
                    return text
                if attempt < 2:
                    if verbose:
                        print(f"   ⚠️  Chapter {chapter_index} too short ({len(text)} chars) — retrying…")
                    time.sleep(2)
            except Exception as e:
                if attempt < 2:
                    wait = 30 if "429" in str(e) or "quota" in str(e).lower() else 5
                    if verbose:
                        print(f"   ⚠️  Chapter {chapter_index} error ({e}) — waiting {wait}s…")
                    time.sleep(wait)
                else:
                    return f"[Chapter {chapter_index}: {chap_title}]\n\n{brief or 'Content unavailable.'}"
        return text

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _chapter_count(self, pages: int) -> int:
        if pages <= 20:   return 4
        if pages <= 40:   return 6
        if pages <= 70:   return 8
        if pages <= 100:  return 10
        if pages <= 150:  return 12
        if pages <= 200:  return 15
        return min(20, pages // 12)

    def _summarize(self, text: str) -> str:
        """Extract a short summary (last 400 chars) for continuation context."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        summary = " ".join(sentences[-4:]) if sentences else text[-400:]
        return summary[:500]

    def _safe_filename(self, title: str) -> str:
        s = re.sub(r'[^\w\s-]', '', title.lower())
        s = re.sub(r'[\s-]+', '_', s).strip('_')
        return s[:60] or "ebook"

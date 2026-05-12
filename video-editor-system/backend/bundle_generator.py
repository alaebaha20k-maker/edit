#!/usr/bin/env python3
"""
Bundle Generator — Parallel Multi-Ebook System
===============================================
Generates N differentiated, professional ebooks from one product brief,
packaged as a ZIP ready to deliver.

Architecture:
  Phase 0 — Bundle Planner  : 1 Gemini call → N differentiated ebook concepts
  Phase 1 — Research         : N parallel Gemini calls (one per ebook)
  Phase 2 — Write Chapters   : All N×C chapters in parallel, gated by Semaphore(8)
  Phase 3 — Build PDFs       : N parallel ReportLab builds (CPU-bound, threadpool)
  Phase 4 — Package          : ZIP + README (1 Gemini call) + manifest.json

Backward compat: EbookGenerator.generate() is untouched.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import google.generativeai as genai

from config import Config
from ebook_generator import EbookGenerator, WORDS_PER_PAGE, RESEARCH_MODEL, WRITE_MODEL

# ---------------------------------------------------------------------------
# Concurrency limits
# ---------------------------------------------------------------------------
MAX_CONCURRENT_CALLS  = Config.MAX_CONCURRENT_CHAPTERS   # 8
_RETRY_WAITS          = (5, 15, 45)                      # exponential backoff


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

class _Progress:
    """Thread-safe progress tracker + printer."""

    def __init__(self, num_ebooks: int, n_chaps: int, verbose: bool) -> None:
        self.num_ebooks  = num_ebooks
        self.n_chaps     = n_chaps
        self.verbose     = verbose
        self._counts     = [0] * num_ebooks   # chapters done per ebook
        self._lock       = asyncio.Lock()

    async def chapter_done(self, ebook_idx: int) -> None:
        async with self._lock:
            self._counts[ebook_idx] += 1
            if self.verbose:
                self._print()

    def _bar(self, done: int, total: int, width: int = 10) -> str:
        filled = int(width * done / total) if total else 0
        return "█" * filled + "░" * (width - filled)

    def _print(self) -> None:
        lines = []
        for i, done in enumerate(self._counts):
            bar = self._bar(done, self.n_chaps)
            lines.append(f"   ├─ Ebook {i+1}/{self.num_ebooks} [{bar}] {done}/{self.n_chaps} chapters")
        # Move cursor up by (previous num_ebooks lines) then reprint
        if hasattr(self, "_printed"):
            sys.stdout.write(f"\033[{self.num_ebooks}A")
        self._printed = True
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()

    def init_rows(self) -> None:
        """Print the initial empty progress rows."""
        if self.verbose:
            self._print()


# ---------------------------------------------------------------------------
# BundleGenerator
# ---------------------------------------------------------------------------

class BundleGenerator:
    """
    Generate a bundle of N differentiated ebooks in parallel.

    Usage::

        gen = BundleGenerator()
        result = gen.generate_bundle(
            bundle_topic="AI side hustles",
            product_details="For complete beginners with no tech background",
            num_ebooks=5,
            pages_per_ebook=30,
        )
        print(result["zip_path"])
    """

    def __init__(self) -> None:
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        # Reuse EbookGenerator helpers (outline parsing, chapter count, etc.)
        self._eg = EbookGenerator()

    # =========================================================================
    # PUBLIC
    # =========================================================================

    def generate_bundle(
        self,
        bundle_topic: str,
        product_details: str,
        num_ebooks: int,
        pages_per_ebook: int,
        audience: str = "general",
        tone: str = "expert",
        language: str = "English",
        verbose: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> Dict:
        """
        Orchestrate the full bundle generation. Synchronous entry point — runs
        the async pipeline inside a new event loop.

        Args:
            progress_callback: Optional ``(pct: int, message: str) -> None``
                called at each phase boundary so callers can track progress
                without polling verbose terminal output.

        Returns a dict with keys: zip_path, bundle_dir, num_ebooks,
        total_words, total_chapters, elapsed.
        """
        num_ebooks      = max(1, min(20, num_ebooks))
        pages_per_ebook = max(5, min(500, pages_per_ebook))
        language        = (language or "English").strip() or "English"

        if verbose:
            print(f"\n{'='*65}")
            print(f"🎯 BUNDLE: {bundle_topic}")
            print(f"{'='*65}")
            print(f"Ebooks  : {num_ebooks}  ·  Pages each: {pages_per_ebook}")
            print(f"Audience: {audience}  ·  Tone: {tone}")
            print(f"Language: {language}")
            print(f"Model   : {WRITE_MODEL}")
            print(f"{'='*65}\n")

        start = time.time()
        result = asyncio.run(
            self._generate_async(
                bundle_topic, product_details, num_ebooks,
                pages_per_ebook, audience, tone, language,
                verbose, start, progress_callback,
            )
        )
        return result

    # =========================================================================
    # ASYNC PIPELINE
    # =========================================================================

    async def _generate_async(
        self,
        bundle_topic: str,
        product_details: str,
        num_ebooks: int,
        pages_per_ebook: int,
        audience: str,
        tone: str,
        language: str,
        verbose: bool,
        wall_start: float,
        progress_callback: Optional[callable] = None,
    ) -> Dict:
        sem = asyncio.Semaphore(MAX_CONCURRENT_CALLS)

        def _report(pct: int, msg: str) -> None:
            if progress_callback:
                try:
                    progress_callback(pct, msg)
                except Exception:
                    pass

        # ── Phase 0: Bundle Planner ───────────────────────────────────────────
        t0 = time.time()
        if verbose:
            print("📋 Phase 0/4 — Planning bundle …")
        _report(5, "📋 Planning bundle…")
        bundle_plan = await asyncio.to_thread(
            self._plan_bundle_sync,
            bundle_topic, product_details, num_ebooks, audience, tone, language,
        )
        if verbose:
            print(f"   ✅ {time.time()-t0:.0f}s — \"{bundle_plan['name']}\"\n")
        _report(15, f"✅ Plan: \"{bundle_plan['name']}\"")

        n_chaps          = self._eg._chapter_count(pages_per_ebook)
        words_target     = pages_per_ebook * WORDS_PER_PAGE
        words_per_chap   = words_target // n_chaps

        # ── Phase 1: Research all ebooks in parallel ──────────────────────────
        t1 = time.time()
        if verbose:
            print(f"🔍 Phase 1/4 — Researching all {num_ebooks} ebooks in parallel …")
        _report(20, f"🔍 Researching {num_ebooks} ebooks in parallel…")
        outlines: List[Dict] = await asyncio.gather(*[
            self._research_one_async(sem, eb, product_details, pages_per_ebook, n_chaps, language)
            for eb in bundle_plan["ebooks"]
        ])
        if verbose:
            print(f"   ✅ {time.time()-t1:.0f}s\n")
        _report(35, f"✅ Research done — {num_ebooks} outlines ready")

        # ── Phase 2: Write all chapters (flat gather, Semaphore gating) ───────
        t2 = time.time()
        total_chaps_to_write = num_ebooks * n_chaps
        if verbose:
            print(f"✍️  Phase 2/4 — Writing {total_chaps_to_write} chapters across {num_ebooks} ebooks ({MAX_CONCURRENT_CALLS} parallel) …")
        _report(38, f"✍️  Writing {total_chaps_to_write} chapters…")
        progress = _Progress(num_ebooks, n_chaps, verbose)
        progress.init_rows()

        # Build flat task list: (ebook_idx, chap_idx, ebook_plan, outline, chap_plan)
        tasks = []
        for ei, (eb_plan, outline) in enumerate(zip(bundle_plan["ebooks"], outlines)):
            prev_sums: List[str] = [""] * n_chaps  # summaries are sequential per ebook
            for ci, chap_plan in enumerate(outline["chapters"]):
                tasks.append(
                    self._write_chapter_async(
                        sem, ei, ci, eb_plan, outline, chap_plan,
                        words_per_chap, n_chaps, progress,
                        product_details=product_details,
                        language=language,
                    )
                )
        flat_results: List[Dict] = await asyncio.gather(*tasks)
        if verbose:
            print(f"   ✅ {time.time()-t2:.0f}s\n")
        _report(74, "✅ All chapters written")

        # Reassemble chapters per ebook (sorted by chap_idx)
        ebooks_chapters: List[List[Dict]] = [[] for _ in range(num_ebooks)]
        for r in flat_results:
            ebooks_chapters[r["ebook_idx"]].append(r)
        for ec in ebooks_chapters:
            ec.sort(key=lambda x: x["chap_idx"])

        # ── Phase 3: Build PDFs (parallel, threadpool) ────────────────────────
        t3 = time.time()
        if verbose:
            print("📄 Phase 3/4 — Building PDFs …")
        _report(78, f"📄 Building {num_ebooks} PDFs…")
        output_dir = Path(Config.BUNDLE_OUTPUT_DIR) / self._slug(bundle_plan["name"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "ebooks").mkdir(exist_ok=True)

        pdf_tasks = [
            asyncio.to_thread(
                self._build_one_pdf,
                i + 1, bundle_plan["ebooks"][i], ebooks_chapters[i],
                output_dir / "ebooks", bundle_plan["name"],
            )
            for i in range(num_ebooks)
        ]
        pdf_results: List[Dict] = await asyncio.gather(*pdf_tasks)
        if verbose:
            print(f"   ✅ {time.time()-t3:.0f}s\n")
        _report(90, "✅ PDFs built")

        # ── Phase 4: Package ──────────────────────────────────────────────────
        t4 = time.time()
        if verbose:
            print("📦 Phase 4/4 — Packaging bundle …")
        _report(93, "📦 Packaging ZIP…")
        from bundle_packager import BundlePackager
        packager = BundlePackager()
        pkg = await asyncio.to_thread(
            packager.package,
            bundle_slug      = self._slug(bundle_plan["name"]),
            bundle_plan      = bundle_plan,
            pdf_results      = pdf_results,
            output_dir       = output_dir,
            language         = language,
            verbose          = verbose,
        )
        if verbose:
            print(f"   ✅ {time.time()-t4:.0f}s\n")
        _report(98, "✅ Bundle packaged")

        elapsed     = time.time() - wall_start
        total_words = sum(r["word_count"] for r in pdf_results)
        total_chaps = sum(r["chapters"] for r in pdf_results)
        m, s        = divmod(int(elapsed), 60)

        if verbose:
            print(f"{'='*65}")
            print(f"✅ DONE: {pkg['zip_path']}")
            print(f"   {num_ebooks} ebooks · {total_chaps} chapters · {total_words:,} words · {m}m {s}s")
            print(f"{'='*65}\n")

        return {
            "success"       : True,
            "zip_path"      : pkg["zip_path"],
            "bundle_dir"    : str(output_dir),
            "num_ebooks"    : num_ebooks,
            "total_words"   : total_words,
            "total_chapters": total_chaps,
            "elapsed"       : round(elapsed, 1),
        }

    # =========================================================================
    # PHASE 0 — BUNDLE PLANNER
    # =========================================================================

    def _plan_bundle_sync(
        self,
        bundle_topic: str,
        product_details: str,
        num_ebooks: int,
        audience: str,
        tone: str,
        language: str = "English",
    ) -> Dict:
        """One Gemini call → bundle blueprint with N differentiated ebook concepts."""
        from ebook_generator import _language_block
        lang_block = _language_block(language)
        prompt = f"""You are a professional ebook bundle strategist.
{lang_block}
BUNDLE TOPIC: "{bundle_topic}"

══════════════════════════════════════════════════════════════
PRODUCT DETAILS — READ EVERY WORD BEFORE DOING ANYTHING ELSE:
══════════════════════════════════════════════════════════════
{product_details}
══════════════════════════════════════════════════════════════

MANDATORY ANALYSIS before planning:
Extract from the Product Details:
  • Every specific product, model, brand, item, or service mentioned
  • The target audience (who they are, their level, situation)
  • The core problem(s) they face
  • The specific outcomes they want
  • Any numbers, specs, constraints, or requirements listed
Every ebook concept below MUST address specific items you identified above.

NUMBER OF EBOOKS: {num_ebooks}
TARGET AUDIENCE: {audience}
TONE: {tone}

YOUR JOB:
Design a cohesive, commercially compelling ebook bundle where EVERY ebook concept is
built from the specific Product Details above — not generic industry content.
Each ebook must:
- Cover a DISTINCT angle drawn from the Product Details — NO overlap in content or approach
- Reference specific items from the Product Details in its title/angle
- Complement the others so buying the bundle delivers far more value than any single ebook
- Have a compelling, specific title that signals concrete value from those details

OUTPUT FORMAT — return ONLY this XML, no other text:

<bundle>
  <name>Bundle name (short, punchy, marketable)</name>
  <positioning>One sentence describing the bundle's unique selling point</positioning>
  <ebooks>
{chr(10).join(f'''    <ebook>
      <number>{i+1}</number>
      <title>Ebook {i+1} title here</title>
      <subtitle>Specific subtitle (one sentence)</subtitle>
      <angle>What makes this ebook's perspective unique</angle>
      <unique_value>Specific outcome the reader gets that NO other ebook in the bundle covers</unique_value>
    </ebook>''' for i in range(num_ebooks))}
  </ebooks>
</bundle>

Rules:
- Titles must be specific and compelling — not generic like "A Complete Guide"
- Each <angle> must be genuinely different (e.g. "strategic", "technical", "psychological", "case study-driven")
- All {num_ebooks} ebook tags must be present and unique"""

        for attempt in range(3):
            try:
                model    = genai.GenerativeModel(RESEARCH_MODEL)
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.7, "max_output_tokens": 8192},
                )
                return self._parse_bundle_plan(response.text.strip(), num_ebooks, bundle_topic)
            except Exception as e:
                wait = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                if attempt < 2:
                    time.sleep(wait)
                else:
                    return self._fallback_bundle_plan(bundle_topic, num_ebooks)
        return self._fallback_bundle_plan(bundle_topic, num_ebooks)

    def _parse_bundle_plan(self, text: str, num_ebooks: int, topic: str) -> Dict:
        def _xml(tag: str, src: str, fallback: str = "") -> str:
            m = re.search(rf'<{tag}>(.*?)</{tag}>', src, re.DOTALL | re.IGNORECASE)
            return m.group(1).strip() if m else fallback

        name        = _xml("name", text, topic)
        positioning = _xml("positioning", text, "")
        ebooks: List[Dict] = []

        for em in re.findall(r'<ebook>(.*?)</ebook>', text, re.DOTALL | re.IGNORECASE):
            ebooks.append({
                "title"        : _xml("title",        em, f"Ebook {len(ebooks)+1}"),
                "subtitle"     : _xml("subtitle",     em, ""),
                "angle"        : _xml("angle",        em, ""),
                "unique_value" : _xml("unique_value", em, ""),
            })

        # Pad if parser missed some
        while len(ebooks) < num_ebooks:
            i = len(ebooks) + 1
            ebooks.append({
                "title"       : f"{topic} — Volume {i}",
                "subtitle"    : f"Essential guide part {i}",
                "angle"       : "comprehensive",
                "unique_value": f"Part {i} content",
            })

        return {"name": name, "positioning": positioning, "ebooks": ebooks[:num_ebooks]}

    def _fallback_bundle_plan(self, topic: str, num_ebooks: int) -> Dict:
        angles = ["foundations", "strategy", "advanced tactics",
                  "case studies", "tools & systems", "psychology",
                  "monetization", "scaling", "productivity", "mastery"]
        ebooks = [
            {
                "title"       : f"{topic}: {angles[i % len(angles)].title()}",
                "subtitle"    : f"A focused guide to {angles[i % len(angles)]}",
                "angle"       : angles[i % len(angles)],
                "unique_value": f"Deep dive into {angles[i % len(angles)]}",
            }
            for i in range(num_ebooks)
        ]
        return {"name": topic, "positioning": topic, "ebooks": ebooks}

    # =========================================================================
    # PHASE 1 — RESEARCH (async, semaphore-gated)
    # =========================================================================

    async def _research_one_async(
        self,
        sem: asyncio.Semaphore,
        eb_plan: Dict,
        product_details: str,
        pages: int,
        n_chaps: int,
        language: str = "English",
    ) -> Dict:
        """Research + outline for one ebook (runs in threadpool, gated by sem)."""
        async with sem:
            return await asyncio.to_thread(
                self._eg._research_and_outline,
                eb_plan["title"],
                f"{product_details}\n\nEBOOK ANGLE: {eb_plan['angle']}\n"
                f"UNIQUE VALUE PROP: {eb_plan['unique_value']}",
                pages, n_chaps, language, False,
            )

    # =========================================================================
    # PHASE 2 — WRITE CHAPTER (async, semaphore-gated)
    # =========================================================================

    async def _write_chapter_async(
        self,
        sem: asyncio.Semaphore,
        ebook_idx: int,
        chap_idx: int,
        eb_plan: Dict,
        outline: Dict,
        chap_plan: Dict,
        words_per_chap: int,
        n_chaps: int,
        progress: _Progress,
        product_details: str = "",
        language: str = "English",
    ) -> Dict:
        """Write one chapter with exponential backoff retry; returns a result dict."""
        prompt = self._build_chapter_prompt(
            eb_plan, outline, chap_plan, chap_idx + 1, n_chaps, words_per_chap,
            product_details, language,
        )
        max_tokens = min(65536, max(int(words_per_chap / 0.75) + 2000, 4000))
        text = ""

        for attempt in range(3):
            async with sem:
                try:
                    text = await asyncio.to_thread(
                        self._gemini_generate_sync,
                        prompt, 0.75, max_tokens,
                    )
                    if len(text) >= int(words_per_chap * 0.5 * 4.5):
                        break          # good length
                    if attempt < 2:
                        await asyncio.sleep(2)
                except Exception as e:
                    wait = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
                        wait = _RETRY_WAITS[min(attempt, len(_RETRY_WAITS) - 1)]
                    else:
                        wait = 5
                    if attempt < 2:
                        await asyncio.sleep(wait)
                    else:
                        text = (f"{chap_plan.get('brief','')}\n\n"
                                f"[Chapter {chap_idx+1}: content unavailable — {e}]")

        await progress.chapter_done(ebook_idx)
        return {
            "ebook_idx": ebook_idx,
            "chap_idx" : chap_idx,
            "title"    : chap_plan["title"],
            "content"  : text,
        }

    def _build_chapter_prompt(
        self,
        eb_plan: Dict,
        outline: Dict,
        chap_plan: Dict,
        chapter_index: int,
        total_chapters: int,
        words_target: int,
        product_details: str = "",
        language: str = "English",
    ) -> str:
        """Build the chapter writing prompt (mirrors EbookGenerator._write_chapter)."""
        from ebook_generator import _language_block
        chap_title = chap_plan["title"]
        key_points = " | ".join(chap_plan.get("key_points", [])) or "Cover topic thoroughly"
        brief      = chap_plan.get("brief", "")
        facts      = chap_plan.get("facts", "")
        is_first   = chapter_index == 1
        is_last    = chapter_index == total_chapters

        position_note = (
            "OPENING CHAPTER: hook the reader immediately, set the stage, establish why this matters."
            if is_first else
            "FINAL CHAPTER: deliver the climax, practical takeaways, strong memorable close."
            if is_last else
            f"MID CHAPTER {chapter_index}/{total_chapters}: deepen the topic, add proof and examples, escalate value."
        )

        lang_block = _language_block(language)
        product_brief_block = (
            f"\n══════════════════════════════════════════════════════════════\n"
            f"PRODUCT DETAILS — ANCHOR EVERY PARAGRAPH TO THIS:\n"
            f"══════════════════════════════════════════════════════════════\n"
            f"{product_details}\n"
            f"══════════════════════════════════════════════════════════════\n"
            f"BEFORE WRITING: Re-read the Product Details above. Every example, tip, fact,\n"
            f"and recommendation must be directly relevant to the specific product, audience,\n"
            f"situation, and outcomes described there. If Product Details names specific items\n"
            f"(products, models, specs, goals) — reference them by name, not generically.\n"
            if product_details else ""
        )

        return f"""You are an expert ebook writer. Write one complete chapter with exceptional quality.
{lang_block}{product_brief_block}
═══════════════════ EBOOK CONTEXT ═══════════════════
EBOOK TITLE: "{eb_plan['title']}"
SUBTITLE: {eb_plan.get('subtitle','')}
UNIQUE ANGLE: {eb_plan.get('angle','')}

═══════════════════ RESEARCH BASE ═══════════════════
{outline['research'][:3000]}
[...full research available above]

═══════════════════ YOUR CHAPTER ═══════════════════
CHAPTER {chapter_index}/{total_chapters}: {chap_title}
KEY POINTS TO COVER: {key_points}
CONTENT BRIEF: {brief}
FACTS/EXAMPLES TO USE: {facts}

═══════════════════ WRITING LAWS ═══════════════════
QUALITY RULES (mandatory):
  ✓ START STRONG: First sentence must grab — no warmup
  ✓ SPECIFICITY: Every claim backed by fact, number, example, or case study
  ✓ VALUE DENSITY: Every paragraph teaches something concrete
  ✓ NO FILLER: Zero padding sentences. Every sentence earns its place.
  ✓ ESCALATION: Each section goes deeper than the last
  ✓ EXPERT VOICE: Write like a practitioner, not a textbook
  ✓ OPENING HOOK: First paragraph = striking fact, bold claim, or vivid scenario
  ✓ CLOSING LINE: End with one memorable forward-driving sentence

MARKDOWN FORMATTING:
  • Section headings: ## Heading (3-5 per chapter, on their own line)
  • Pull-quotes: > Your insight here (1-2 per chapter, punchy)
  • Bullet lists: ONLY for 3+ parallel items, max once per chapter, use - item
  • Do NOT write the chapter title itself — the system adds it

STYLE: Direct, authoritative, practical. Like a knowledgeable mentor.
FORBIDDEN: "In this chapter", "As we discussed", "It is important to note"

POSITION: {position_note}

═══════════════════ LENGTH ═══════════════════
TARGET: {words_target} words (min {int(words_target*0.9)}, max {int(words_target*1.1)})
WRITE THE CHAPTER NOW:"""

    # =========================================================================
    # PHASE 3 — BUILD PDF (sync, called via to_thread)
    # =========================================================================

    def _build_one_pdf(
        self,
        ebook_num: int,
        eb_plan: Dict,
        chapter_results: List[Dict],
        ebooks_dir: Path,
        bundle_name: str,
    ) -> Dict:
        """Build one ebook PDF. Returns metadata dict."""
        from pdf_builder import EbookPDFBuilder
        chapters = [{"title": r["title"], "content": r["content"]} for r in chapter_results]
        slug     = self._eg._safe_filename(eb_plan["title"])
        filename = f"{ebook_num:02d}_{slug}.pdf"
        pdf_path = ebooks_dir / filename

        builder = EbookPDFBuilder()
        builder.build(
            title       = eb_plan["title"],
            subtitle    = eb_plan.get("subtitle", ""),
            chapters    = chapters,
            output_path = pdf_path,
            bundle_name = bundle_name,
        )

        word_count = sum(len(r["content"].split()) for r in chapter_results)
        return {
            "ebook_num"  : ebook_num,
            "filename"   : filename,
            "pdf_path"   : str(pdf_path),
            "title"      : eb_plan["title"],
            "subtitle"   : eb_plan.get("subtitle", ""),
            "angle"      : eb_plan.get("angle", ""),
            "word_count" : word_count,
            "chapters"   : len(chapters),
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _gemini_generate_sync(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Blocking Gemini call. Intended to run inside asyncio.to_thread."""
        model    = genai.GenerativeModel(WRITE_MODEL)
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature"      : temperature,
                "max_output_tokens": max_tokens,
                "top_p"            : 0.95,
            },
        )
        return response.text.strip()

    def _slug(self, name: str) -> str:
        s = re.sub(r'[^\w\s-]', '', name.lower())
        s = re.sub(r'[\s-]+', '_', s).strip('_')
        return s[:50] or "bundle"

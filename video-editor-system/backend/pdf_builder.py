#!/usr/bin/env python3
"""
PDF Builder — Clean professional ebook template using reportlab.

Template:
  • Dark navy cover page with title, subtitle, generation date
  • Table of contents
  • Chapter pages: header bar, styled body text, page numbers in footer
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white, black
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    PageBreak, Table, TableStyle, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus.frames import Frame as RLFrame

# ── Colour palette ────────────────────────────────────────────────────────────
NAVY        = HexColor("#0F172A")
NAVY_LIGHT  = HexColor("#1E293B")
ACCENT      = HexColor("#6366F1")   # indigo
WHITE       = HexColor("#F8FAFC")
MUTED       = HexColor("#64748B")
BODY_CLR    = HexColor("#1E1E1E")
SECTION_CLR = HexColor("#0F172A")
TOC_DOTS    = HexColor("#E2E8F0")

PAGE_W, PAGE_H = A4  # 595.28 x 841.89 points
ML = MR = 20 * mm
MT = MB = 22 * mm
TW = PAGE_W - ML - MR


# =============================================================================
# COVER PAGE (canvas-drawn, not flowable)
# =============================================================================

def _draw_cover(canvas, doc, title: str, subtitle: str, n_chapters: int):
    c = canvas
    w, h = PAGE_W, PAGE_H

    # Background
    c.setFillColor(NAVY)
    c.rect(0, 0, w, h, fill=1, stroke=0)

    # Top accent bar
    c.setFillColor(ACCENT)
    c.rect(0, h - 8 * mm, w, 8 * mm, fill=1, stroke=0)

    # Bottom accent bar
    c.rect(0, 0, w, 8 * mm, fill=1, stroke=0)

    # Title
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 34)
    # Word-wrap title manually
    words = title.split()
    lines, line = [], []
    for w_word in words:
        test = " ".join(line + [w_word])
        if c.stringWidth(test, "Helvetica-Bold", 34) < TW:
            line.append(w_word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [w_word]
    if line:
        lines.append(" ".join(line))

    y = h * 0.62 + len(lines) * 22
    for l in lines:
        c.drawCentredString(PAGE_W / 2, y, l)
        y -= 38

    # Decorative line below title
    c.setStrokeColor(ACCENT)
    c.setLineWidth(3)
    line_w = 120 * mm
    c.line((PAGE_W - line_w) / 2, y - 6, (PAGE_W + line_w) / 2, y - 6)

    # Subtitle
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#B0BEC5"))
    sub_lines = _wrap_text(subtitle, "Helvetica", 12, TW, c)
    sy = y - 28
    for sl in sub_lines[:4]:
        c.drawCentredString(PAGE_W / 2, sy, sl)
        sy -= 18

    # Meta line
    c.setFont("Helvetica", 10)
    c.setFillColor(HexColor("#78909C"))
    year = datetime.now().year
    meta = f"{n_chapters} Chapters  ·  {year}  ·  Complete Guide"
    c.drawCentredString(PAGE_W / 2, 28 * mm, meta)


def _wrap_text(text: str, font: str, size: float, max_w: float, canvas) -> List[str]:
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        if canvas.stringWidth(test, font, size) <= max_w:
            line.append(word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [word]
    if line:
        lines.append(" ".join(line))
    return lines


# =============================================================================
# PAGE TEMPLATE CALLBACKS
# =============================================================================

def _body_page(canvas, doc):
    """Footer for body pages."""
    c = canvas
    c.saveState()
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(MUTED)
    c.drawString(ML, MB * 0.6, doc.ebook_title[:60])
    c.drawRightString(PAGE_W - MR, MB * 0.6, f"Page {doc.page}")
    c.restoreState()


# =============================================================================
# MAIN BUILDER
# =============================================================================

class EbookPDFBuilder:

    def build(
        self,
        title: str,
        subtitle: str,
        chapters: List[Dict],
        output_path: Path,
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Document setup ────────────────────────────────────────────────────
        doc = BaseDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=ML, rightMargin=MR,
            topMargin=MT, bottomMargin=MB,
        )
        doc.ebook_title = title[:60]

        body_frame = RLFrame(ML, MB, TW, PAGE_H - MT - MB, id="body")

        cover_tmpl = PageTemplate(id="cover", frames=[body_frame],
                                  onPage=lambda c, d: None)
        body_tmpl  = PageTemplate(id="body",  frames=[body_frame],
                                  onPage=_body_page)
        doc.addPageTemplates([cover_tmpl, body_tmpl])

        styles = self._make_styles()
        story  = []

        # ── Cover (drawn via onFirstPage trick) ───────────────────────────────
        story.append(_CoverDrawable(title, subtitle, len(chapters)))
        story.append(PageBreak())

        # Switch to body template
        from reportlab.platypus import NextPageTemplate
        story.append(NextPageTemplate("body"))

        # ── Table of Contents ─────────────────────────────────────────────────
        story += self._build_toc(chapters, styles)
        story.append(PageBreak())

        # ── Chapters ──────────────────────────────────────────────────────────
        for i, chap in enumerate(chapters, 1):
            story += self._build_chapter(i, len(chapters), chap["title"], chap["content"], styles)
            story.append(PageBreak())

        doc.build(story)
        return output_path

    # =========================================================================
    # TOC
    # =========================================================================

    def _build_toc(self, chapters: List[Dict], styles: dict) -> list:
        items = []
        # TOC header bar
        items.append(_HeaderBar("Table of Contents"))
        items.append(Spacer(1, 10 * mm))

        for i, chap in enumerate(chapters, 1):
            chap_title = chap["title"][:70]
            row_data = [
                [Paragraph(f'<font color="#6366F1"><b>{i:02d}</b></font>', styles["toc_num"]),
                 Paragraph(chap_title, styles["toc_title"]),
                 Paragraph(f'<font color="#64748B">{i * 2 + 2}</font>', styles["toc_pg"])],
            ]
            t = Table(row_data, colWidths=[12 * mm, TW - 30 * mm, 18 * mm])
            t.setStyle(TableStyle([
                ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, 0),  0.5, TOC_DOTS),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING",    (0, 0), (-1, 0), 4),
            ]))
            items.append(t)

        return items

    # =========================================================================
    # CHAPTER
    # =========================================================================

    def _build_chapter(
        self,
        num: int,
        total: int,
        title: str,
        content: str,
        styles: dict,
    ) -> list:
        items = []

        # Chapter header bar
        items.append(_ChapterHeaderBar(num, title))
        items.append(Spacer(1, 8 * mm))

        # Chapter body
        paragraphs = self._split_paragraphs(content)
        for para in paragraphs:
            if not para:
                continue
            if self._is_section_heading(para):
                items.append(Spacer(1, 3 * mm))
                items.append(Paragraph(para.rstrip(":"), styles["section_head"]))
                items.append(Spacer(1, 2 * mm))
            else:
                items.append(Paragraph(para, styles["body"]))
                items.append(Spacer(1, 3 * mm))

        return items

    # =========================================================================
    # STYLES
    # =========================================================================

    def _make_styles(self) -> dict:
        return {
            "body": ParagraphStyle(
                "body", fontName="Helvetica", fontSize=11,
                leading=17, textColor=BODY_CLR,
                alignment=TA_JUSTIFY,
                spaceAfter=4,
            ),
            "section_head": ParagraphStyle(
                "section_head", fontName="Helvetica-Bold", fontSize=13,
                leading=18, textColor=SECTION_CLR,
                spaceBefore=6, spaceAfter=3,
            ),
            "toc_num": ParagraphStyle(
                "toc_num", fontName="Helvetica-Bold", fontSize=10,
                leading=14, textColor=ACCENT,
            ),
            "toc_title": ParagraphStyle(
                "toc_title", fontName="Helvetica", fontSize=11,
                leading=14, textColor=BODY_CLR,
            ),
            "toc_pg": ParagraphStyle(
                "toc_pg", fontName="Helvetica-Oblique", fontSize=9,
                leading=14, textColor=MUTED, alignment=TA_CENTER,
            ),
        }

    # =========================================================================
    # TEXT HELPERS
    # =========================================================================

    def _split_paragraphs(self, text: str) -> List[str]:
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*',     r'\1', text)
        text = re.sub(r'#{1,6}\s*',     '',    text)
        text = re.sub(r'`(.+?)`',       r'\1', text)
        # Escape reportlab XML special chars
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]

    def _is_section_heading(self, para: str) -> bool:
        # Must unescape to check
        plain = para.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        words = plain.split()
        if len(words) > 10:
            return False
        if plain.endswith(":") and len(words) <= 8:
            return True
        if plain.isupper() and 2 <= len(words) <= 8:
            return True
        return False


# =============================================================================
# CUSTOM FLOWABLES
# =============================================================================

class _CoverDrawable:
    """Draws the full cover page using canvas ops (not a standard Flowable)."""

    def __init__(self, title: str, subtitle: str, n_chapters: int):
        self.title      = title
        self.subtitle   = subtitle
        self.n_chapters = n_chapters

    def wrap(self, availWidth, availHeight):
        return (availWidth, availHeight)

    def drawOn(self, canvas, x, y, _sW=0):
        _draw_cover(canvas, None, self.title, self.subtitle, self.n_chapters)

    def split(self, availWidth, availHeight):
        return [self]

    def identity(self, maxLen=None):
        return "CoverDrawable"


class _HeaderBar:
    """TOC header bar flowable."""

    def __init__(self, text: str):
        self.text = text

    def wrap(self, availWidth, availHeight):
        return (availWidth, 14 * mm)

    def drawOn(self, canvas, x, y, _sW=0):
        c = canvas
        c.saveState()
        c.setFillColor(NAVY_LIGHT)
        c.rect(x, y, TW, 14 * mm, fill=1, stroke=0)
        c.setFillColor(ACCENT)
        c.rect(x, y, 4, 14 * mm, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(WHITE)
        c.drawString(x + 10, y + 4 * mm, self.text)
        c.restoreState()

    def split(self, *args):
        return [self]


class _ChapterHeaderBar:
    """Chapter header bar with chapter number and title."""

    def __init__(self, num: int, title: str):
        self.num   = num
        self.title = title[:55] + ("…" if len(title) > 55 else "")

    def wrap(self, availWidth, availHeight):
        return (availWidth, 20 * mm)

    def drawOn(self, canvas, x, y, _sW=0):
        c = canvas
        c.saveState()
        # Dark header background
        c.setFillColor(NAVY_LIGHT)
        c.rect(x, y, TW, 20 * mm, fill=1, stroke=0)
        # Accent left bar
        c.setFillColor(ACCENT)
        c.rect(x, y, 5, 20 * mm, fill=1, stroke=0)
        # Accent bottom line
        c.rect(x, y, TW, 2, fill=1, stroke=0)
        # Chapter label
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(ACCENT)
        c.drawString(x + 12, y + 14 * mm, f"CHAPTER {self.num:02d}")
        # Chapter title
        c.setFont("Helvetica-Bold", 16)
        c.setFillColor(WHITE)
        c.drawString(x + 12, y + 6 * mm, self.title)
        c.restoreState()

    def split(self, *args):
        return [self]

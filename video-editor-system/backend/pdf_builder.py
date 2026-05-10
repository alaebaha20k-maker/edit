#!/usr/bin/env python3
"""
PDF Builder — Premium Ebook Template v2
========================================
Enhancements:
  • Two-pass TOC with real page numbers (multiBuild + _PageCollector)
  • Leader dots and internal PDF clickable links in TOC
  • Redesigned title page: centered, gold frame corners, ornamental dots
  • Chapter opener: "CHAPTER ONE" spelled out, centered, no giant watermark
  • Body text: serif 11pt, 1.5 leading, 6pt paragraph spacing
  • TOC pages have no page number; body pages do
  • Inline markdown (**bold**, *italic*) rendered in paragraphs
"""

from __future__ import annotations

import re
import copy
import xml.etree.ElementTree as _ET
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer,
    PageBreak, Table, TableStyle, Flowable,
    NextPageTemplate, KeepTogether,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus.frames import Frame as RLFrame

# ── Register serif fonts ───────────────────────────────────────────────────────
_FONT_MAP = {
    "Serif":        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "Serif-Bold":   "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "Serif-Italic": "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
}
_serif_ok = True
for _name, _path in _FONT_MAP.items():
    try:
        pdfmetrics.registerFont(TTFont(_name, _path))
    except Exception:
        _serif_ok = False

if _serif_ok:
    try:
        pdfmetrics.registerFontFamily(
            "Serif",
            normal="Serif",
            bold="Serif-Bold",
            italic="Serif-Italic",
            boldItalic="Serif-Bold",
        )
    except Exception:
        _serif_ok = False

# Safe font aliases — fall back to built-in Helvetica if DejaVu not available
F_SERIF      = "Serif"        if _serif_ok else "Helvetica"
F_SERIF_BOLD = "Serif-Bold"   if _serif_ok else "Helvetica-Bold"
F_SERIF_ITAL = "Serif-Italic" if _serif_ok else "Helvetica-Oblique"

# ── Palette ────────────────────────────────────────────────────────────────────
NAVY        = HexColor("#080E1C")
NAVY_MID    = HexColor("#0F1828")
NAVY_CARD   = HexColor("#14202F")
INDIGO      = HexColor("#4A5BE0")
INDIGO_SOFT = HexColor("#6270E8")
INDIGO_BG   = HexColor("#EEF0FD")
GOLD        = HexColor("#C9950A")
GOLD_LIGHT  = HexColor("#E8B020")
GOLD_BG     = HexColor("#FDF7E3")
WHITE       = HexColor("#EDF2FF")
OFF_WHITE   = HexColor("#F8FAFB")
BODY_CLR    = HexColor("#18202E")
MUTED       = HexColor("#64748B")
RULE_CLR    = HexColor("#CBD5E1")
H1_CLR      = HexColor("#1E3A5F")
H2_CLR      = HexColor("#4A5BE0")
DIVIDER_LN  = HexColor("#CBD5E1")
QUOTE_BG    = HexColor("#F0F3FF")
CALLOUT_BG  = HexColor("#FFFBEB")
CALLOUT_TOP = HexColor("#C9950A")
BORDER_CLR  = HexColor("#E2E8F0")

PAGE_W, PAGE_H = A4
BORDER_INSET = 8 * mm
ML = MR = 22 * mm
MT = 25 * mm
MB = 25 * mm
TW = PAGE_W - ML - MR

# ── Chapter number words ───────────────────────────────────────────────────────
_NUM_WORDS = [
    "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE",
    "TEN", "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN",
    "SEVENTEEN", "EIGHTEEN", "NINETEEN", "TWENTY",
]

def _chapter_word(n: int) -> str:
    return _NUM_WORDS[n - 1] if 1 <= n <= 20 else str(n)


# ── Page number collector — identity-preserved across deepcopy ─────────────────
class _PageCollector:
    def __init__(self):
        self._data: Dict[int, int] = {}

    def set(self, idx: int, page: int) -> None:
        self._data[idx] = page

    def get(self, idx: int, default="") -> str:
        v = self._data.get(idx)
        return str(v) if v is not None else str(default)

    def __deepcopy__(self, memo):
        return self   # share the same instance across multiBuild passes


# =============================================================================
# CANVAS UTILITIES
# =============================================================================

def _wrap_canvas(text: str, font: str, size: float, max_w: float, c) -> List[str]:
    words = text.split()
    lines, line = [], []
    for word in words:
        test = " ".join(line + [word])
        if c.stringWidth(test, font, size) <= max_w:
            line.append(word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [word]
    if line:
        lines.append(" ".join(line))
    return lines or [""]


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline_md(text: str) -> str:
    """Convert inline markdown to ReportLab XML: **bold**, *italic*.

    Triple markers (***) are processed before double (**) so that nested
    bold+italic patterns are handled correctly.  Single-marker patterns use
    a character class [^*<>] / [^_<>] to prevent matching across already-
    inserted XML tags, which previously caused malformed nesting like
    <b><i></b></i> that crashed ReportLab's XML parser.
    """
    t = _esc(text)
    # Bold+italic — triple markers MUST come before double
    t = re.sub(r'\*{3}(.+?)\*{3}', r'<b><i>\1</i></b>', t)
    t = re.sub(r'_{3}(.+?)_{3}',   r'<b><i>\1</i></b>', t)
    # Bold
    t = re.sub(r'\*{2}(.+?)\*{2}', r'<b>\1</b>', t)
    t = re.sub(r'_{2}(.+?)_{2}',   r'<b>\1</b>', t)
    # Italic — [^*<>] / [^_<>] stops the match at any existing XML tag
    # boundary, so it can never produce cross-nested tags
    t = re.sub(r'(?<!\*)\*(?!\*)([^*<>]+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', t)
    t = re.sub(r'(?<!_)_(?!_)([^_<>]+?)(?<!_)_(?!_)',       r'<i>\1</i>', t)
    # Final safety: parse result as XML; strip all markup if it's still malformed
    try:
        _ET.fromstring(f'<r>{t}</r>')
    except _ET.ParseError:
        t = re.sub(r'<[^>]+>', '', t)
    return t


def _safe_para(xml_text: str, style) -> "Paragraph":
    """Build a Paragraph, falling back to plain text if XML is malformed."""
    try:
        return Paragraph(xml_text, style)
    except Exception:
        plain = re.sub(r'<[^>]+>', '', xml_text)
        return Paragraph(plain, style)


def _letter_space(text: str, font: str, size: float, spacing: float, c, x: float, y: float) -> None:
    """Draw text with extra letter spacing."""
    for ch in text:
        c.drawString(x, y, ch)
        x += c.stringWidth(ch, font, size) + spacing


# =============================================================================
# COVER  (redesigned: centered, gold frame corners, ornamental dots)
# =============================================================================

def _draw_cover(canvas, doc):
    c = canvas
    W, H = PAGE_W, PAGE_H

    title       = getattr(doc, "_cover_title",       "Ebook")
    subtitle    = getattr(doc, "_cover_subtitle",    "")
    bundle_name = getattr(doc, "_cover_bundle_name", "")
    year        = str(datetime.now().year)

    # ── Dark navy background ─────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Dot-grid texture ─────────────────────────────────────────────────────
    c.setFillColor(HexColor("#0E1830"))
    ds = 14
    for row in range(int(H / ds) + 1):
        for col in range(int(W / ds) + 1):
            c.circle(col * ds, row * ds, 0.7, fill=1, stroke=0)

    # ── Geometric accent triangles top-right ─────────────────────────────────
    for colour, pts in [
        (NAVY_MID,  [(W * 0.38, H), (W, H), (W, H * 0.50)]),
        (NAVY_CARD, [(W * 0.58, H), (W, H), (W, H * 0.65)]),
        (INDIGO,    [(W * 0.73, H), (W, H), (W, H * 0.77)]),
        (GOLD,      [(W * 0.86, H), (W, H), (W, H * 0.88)]),
    ]:
        c.setFillColor(colour)
        p = c.beginPath()
        p.moveTo(*pts[0]); p.lineTo(*pts[1]); p.lineTo(*pts[2]); p.close()
        c.drawPath(p, fill=1, stroke=0)

    # ── Bottom indigo bar + gold accent ──────────────────────────────────────
    c.setFillColor(INDIGO)
    c.rect(0, 0, W, 12 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, 0, 20 * mm, 12 * mm, fill=1, stroke=0)

    # ── Left gold bar ────────────────────────────────────────────────────────
    c.setFillColor(GOLD)
    c.rect(0, 12 * mm, 4, H - 12 * mm, fill=1, stroke=0)

    # ── Gold frame corners ────────────────────────────────────────────────────
    inset  = 10 * mm
    corner = 10 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.2)
    for (sx, sy, ex1, ey1, ex2, ey2) in [
        (inset,     H - inset, inset + corner, H - inset, inset,     H - inset - corner),  # TL
        (W - inset, H - inset, W - inset - corner, H - inset, W - inset, H - inset - corner),  # TR
        (inset,     inset,     inset + corner, inset,     inset,     inset + corner),  # BL
        (W - inset, inset,     W - inset - corner, inset, W - inset, inset + corner),  # BR
    ]:
        c.line(sx, sy, ex1, ey1)
        c.line(sx, sy, ex2, ey2)

    # ── Bundle name (small caps, letter-spaced, faded, top area) ────────────
    if bundle_name:
        bn = bundle_name.upper()[:50]
        c.setFont("Helvetica", 7)
        c.setFillColor(HexColor("#2E4565"))
        bn_w = c.stringWidth(bn, "Helvetica", 7) + 2.5 * (len(bn) - 1)
        _letter_space(bn, "Helvetica", 7, 2.5, c, W / 2 - bn_w / 2, H * 0.84)

    # ── Title (upper-third, centered, large bold serif 28pt) ─────────────────
    c.setFillColor(WHITE)
    title_lines = _wrap_canvas(title, F_SERIF_BOLD, 28, W - 4 * ML, c)
    y = H * 0.68
    for ln in title_lines:
        c.setFont(F_SERIF_BOLD, 28)
        c.drawCentredString(W / 2, y, ln)
        y -= 37

    # ── Thin centered divider (40% page width) ────────────────────────────────
    y -= 6
    div_w = W * 0.40
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.8)
    c.line(W / 2 - div_w / 2, y, W / 2 + div_w / 2, y)
    y -= 14

    # ── Subtitle (italic, medium blue-gray, 13pt) ─────────────────────────────
    if subtitle:
        c.setFont(F_SERIF_ITAL, 12)
        c.setFillColor(HexColor("#6B8BAF"))
        sub_lines = _wrap_canvas(subtitle, F_SERIF_ITAL, 12, W - 4 * ML, c)
        for sl in sub_lines[:3]:
            c.drawCentredString(W / 2, y, sl)
            y -= 17
        y -= 4

    # ── Three ornamental dots ● ● ● ──────────────────────────────────────────
    c.setFillColor(GOLD)
    for dx in [-10, 0, 10]:
        c.circle(W / 2 + dx, y - 4, 2.2, fill=1, stroke=0)

    # ── Year (bottom center, faded) ───────────────────────────────────────────
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#2E4565"))
    c.drawCentredString(W / 2, 17 * mm, year)


# =============================================================================
# CHAPTER OPENER  (elegant: "CHAPTER ONE" spelled out, centered, clean)
# =============================================================================

def _draw_chapter_opener(canvas, doc):
    c = canvas
    W, H = PAGE_W, PAGE_H
    num   = getattr(doc, "_opener_num",   1)
    title = getattr(doc, "_opener_title", "")

    # ── Dark background ───────────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Subtle dot texture ────────────────────────────────────────────────────
    c.setFillColor(HexColor("#0E1830"))
    ds = 18
    for row in range(int(H / ds) + 1):
        for col in range(int(W / ds) + 1):
            c.circle(col * ds, row * ds, 0.6, fill=1, stroke=0)

    # ── Left gold bar ─────────────────────────────────────────────────────────
    c.setFillColor(GOLD)
    c.rect(0, 0, 4, H, fill=1, stroke=0)

    # ── Indigo bottom bar ─────────────────────────────────────────────────────
    c.setFillColor(INDIGO)
    c.rect(0, 0, W, 10 * mm, fill=1, stroke=0)

    # ── "CHAPTER ONE" label — small caps, letter-spaced, light gray, centered
    label = f"CHAPTER  {_chapter_word(num)}"
    c.setFont("Helvetica", 9.5)
    c.setFillColor(HexColor("#3A567A"))
    lbl_w = c.stringWidth(label, "Helvetica", 9.5) + 2.5 * (len(label) - 1)
    _letter_space(label, "Helvetica", 9.5, 2.5, c, W / 2 - lbl_w / 2, H * 0.60)

    # ── Thin centered rule below label ───────────────────────────────────────
    rule_y = H * 0.60 - 9
    rule_w = 55 * mm
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.9)
    c.line(W / 2 - rule_w / 2, rule_y, W / 2 + rule_w / 2, rule_y)

    # ── Chapter title (large serif bold, centered, white) ─────────────────────
    c.setFillColor(WHITE)
    title_lines = _wrap_canvas(title, F_SERIF_BOLD, 26, W - 2 * ML - 12, c)
    y = rule_y - 20
    for ln in title_lines:
        c.setFont(F_SERIF_BOLD, 26)
        c.drawCentredString(W / 2, y, ln)
        y -= 34


# =============================================================================
# PAGE CALLBACKS
# =============================================================================

def _cover_cb(canvas, doc):
    _draw_cover(canvas, doc)


def _opener_cb(canvas, doc):
    _draw_chapter_opener(canvas, doc)


def _toc_cb(canvas, doc):
    """TOC pages: border + header rule but NO page number in footer."""
    c = canvas
    c.saveState()

    c.setStrokeColor(BORDER_CLR)
    c.setLineWidth(0.4)
    inset = BORDER_INSET
    c.rect(inset, inset, PAGE_W - 2 * inset, PAGE_H - 2 * inset, fill=0, stroke=1)

    # Footer rule only (no page number, no ebook title)
    c.setStrokeColor(RULE_CLR)
    c.setLineWidth(0.5)
    c.line(ML, MB * 0.85, PAGE_W - MR, MB * 0.85)

    c.restoreState()


def _body_cb(canvas, doc):
    c = canvas
    c.saveState()

    # ── Page border ───────────────────────────────────────────────────────────
    c.setStrokeColor(BORDER_CLR)
    c.setLineWidth(0.4)
    inset = BORDER_INSET
    c.rect(inset, inset, PAGE_W - 2 * inset, PAGE_H - 2 * inset, fill=0, stroke=1)

    # ── Running header ────────────────────────────────────────────────────────
    chap_title = getattr(doc, "_current_chapter", "")[:55]
    if chap_title:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUTED)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 14 * mm, chap_title)
        c.setStrokeColor(RULE_CLR)
        c.setLineWidth(0.4)
        c.line(ML, PAGE_H - 15.5 * mm, PAGE_W - MR, PAGE_H - 15.5 * mm)

    # ── Footer rule ───────────────────────────────────────────────────────────
    c.setStrokeColor(RULE_CLR)
    c.setLineWidth(0.5)
    c.line(ML, MB * 0.85, PAGE_W - MR, MB * 0.85)

    # Footer: ebook title left, page number right
    c.setFont(F_SERIF_ITAL, 7.5)
    c.setFillColor(MUTED)
    c.drawString(ML, MB * 0.48, getattr(doc, "ebook_title", "")[:52])

    c.setFont("Helvetica-Bold", 8.5)
    c.setFillColor(INDIGO)
    c.drawRightString(PAGE_W - MR, MB * 0.48, str(doc.page))

    c.restoreState()


# =============================================================================
# CUSTOM FLOWABLES
# =============================================================================

class _CoverPlaceholder(Flowable):
    def wrap(self, aw, ah): return (aw, ah)
    def draw(self): pass


class _OpenerPlaceholder(Flowable):
    def wrap(self, aw, ah): return (aw, ah)
    def draw(self): pass


class _ChapterAnchor(Flowable):
    """Zero-height flowable: records page number + creates PDF bookmark."""
    def __init__(self, idx: int, collector: _PageCollector):
        super().__init__()
        self.idx       = idx
        self.collector = collector
        self.width     = 0
        self.height    = 0

    def wrap(self, aw, ah): return (0, 0)

    def draw(self):
        key = f"chapter_{self.idx}"
        self.canv.bookmarkPage(key, fit="XYZ", left=0, top=PAGE_H, zoom=0)
        self.collector.set(self.idx, self.canv.getPageNumber())


class _TocHeader(Flowable):
    H = 18 * mm

    def wrap(self, aw, ah):
        self._aw = aw
        return (aw, self.H)

    def draw(self):
        c  = self.canv
        aw = self._aw
        c.setFillColor(NAVY)
        c.rect(0, 0, aw, self.H, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.rect(0, 0, 4, self.H, fill=1, stroke=0)
        c.setFillColor(INDIGO)
        c.rect(0, 0, aw, 2, fill=1, stroke=0)
        c.setFont(F_SERIF_BOLD, 16)
        c.setFillColor(WHITE)
        c.drawString(13, 6.5 * mm, "Table of Contents")


class _TocRow(Flowable):
    """One TOC entry: number · leader dots · page number, with internal link."""
    ROW_H = 11 * mm

    def __init__(self, idx: int, title: str, collector: _PageCollector):
        super().__init__()
        self.idx       = idx
        self.title     = title
        self.collector = collector

    def wrap(self, aw, ah):
        self._aw = aw
        return (aw, self.ROW_H)

    def draw(self):
        c   = self.canv
        aw  = self._aw
        y   = 3.5 * mm   # text baseline from bottom of row

        # Bottom divider
        c.setStrokeColor(HexColor("#E2EAF4"))
        c.setLineWidth(0.4)
        c.line(0, 0, aw, 0)

        # Chapter number (gold, serif bold)
        num_str = f"{self.idx:02d}"
        c.setFont(F_SERIF_BOLD, 12)
        c.setFillColor(GOLD)
        c.drawString(0, y, num_str)
        num_w = 13 * mm

        # Page number (right-aligned, indigo)
        pg_str = self.collector.get(self.idx)
        pg_w = 0
        if pg_str:
            c.setFont("Helvetica-Bold", 9.5)
            c.setFillColor(INDIGO)
            c.drawRightString(aw, y, pg_str)
            pg_w = c.stringWidth(pg_str, "Helvetica-Bold", 9.5) + 5

        # Title (truncated to fit available space)
        title   = self.title
        max_w   = aw - num_w - pg_w - 18
        c.setFont("Helvetica", 10.5)
        while len(title) > 5 and c.stringWidth(title, "Helvetica", 10.5) > max_w:
            title = title[:-1]
        title_w = c.stringWidth(title, "Helvetica", 10.5)
        c.setFillColor(BODY_CLR)
        c.drawString(num_w, y, title)

        # Leader dots between title end and page number
        dot_x = num_w + title_w + 4
        dot_end = aw - pg_w - 3
        c.setFont("Helvetica", 7.5)
        c.setFillColor(HexColor("#A8BAC8"))
        x = dot_x
        while x + 4 < dot_end:
            c.drawString(x, y + 0.5, ".")
            x += 4.5

        # Internal PDF link — covers entire row
        if pg_str:
            try:
                ctm = c._currentMatrix
                ax, ay = ctm[4], ctm[5]
                c.linkAbsolute(
                    "", f"chapter_{self.idx}",
                    (ax, ay, ax + aw, ay + self.ROW_H),
                    thickness=0, Kind="GoTo",
                )
            except Exception:
                pass


class _H1Bar(Flowable):
    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def wrap(self, aw, ah):
        self._aw = aw
        return (aw, 11 * mm)

    def draw(self):
        c = self.canv
        c.setFillColor(INDIGO_BG)
        c.rect(0, 0, self._aw, 11 * mm, fill=1, stroke=0)
        c.setFillColor(INDIGO)
        c.rect(0, 0, 4, 11 * mm, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.rect(0, 11 * mm - 4, 4, 4, fill=1, stroke=0)
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(H1_CLR)
        c.drawString(11, 4 * mm, self.text[:74])


class _SectionDivider(Flowable):
    def wrap(self, aw, ah):
        self._aw = aw
        return (aw, 9 * mm)

    def draw(self):
        c   = self.canv
        mid = self._aw / 2
        cy  = 4.5 * mm
        c.setStrokeColor(DIVIDER_LN)
        c.setLineWidth(0.6)
        c.line(0, cy, mid - 14, cy)
        c.line(mid + 14, cy, self._aw, cy)
        c.setFillColor(INDIGO)
        c.circle(mid, cy, 3.5, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.circle(mid - 11, cy, 1.8, fill=1, stroke=0)
        c.circle(mid + 11, cy, 1.8, fill=1, stroke=0)
        c.setFillColor(DIVIDER_LN)
        c.circle(mid - 22, cy, 1.2, fill=1, stroke=0)
        c.circle(mid + 22, cy, 1.2, fill=1, stroke=0)


class _PullQuote(Flowable):
    def __init__(self, text: str, style):
        super().__init__()
        self._text  = text
        self._style = style

    def wrap(self, aw, ah):
        self._aw   = aw
        self._para = _safe_para(_inline_md(self._text), self._style)
        pw, ph     = self._para.wrap(aw - 22, ah)
        self._ph   = ph
        return (aw, ph + 9 * mm)

    def draw(self):
        c = self.canv
        h = self._ph + 9 * mm
        c.setFillColor(QUOTE_BG)
        c.roundRect(0, 0, self._aw, h, 4, fill=1, stroke=0)
        c.setFillColor(INDIGO)
        c.rect(0, 0, 4, h, fill=1, stroke=0)
        c.setFont(F_SERIF_BOLD, 28)
        c.setFillColor(HexColor("#C0C8F0"))
        c.drawString(10, h - 10 * mm, "“")
        self._para.drawOn(c, 16, 4.5 * mm)


class _CalloutBox(Flowable):
    def __init__(self, label: str, text: str, style):
        super().__init__()
        self._label = label.upper()
        self._text  = text
        self._style = style

    def wrap(self, aw, ah):
        self._aw   = aw
        self._para = _safe_para(_inline_md(self._text), self._style)
        pw, ph     = self._para.wrap(aw - 20, ah)
        self._ph   = ph
        return (aw, ph + 14 * mm)

    def draw(self):
        c  = self.canv
        h  = self._ph + 14 * mm
        aw = self._aw
        c.setFillColor(CALLOUT_BG)
        c.roundRect(0, 0, aw, h, 5, fill=1, stroke=0)
        c.setFillColor(GOLD)
        c.roundRect(0, h - 8 * mm, aw, 8 * mm, 5, fill=1, stroke=0)
        c.rect(0, h - 8 * mm - 4, aw, 4, fill=1, stroke=0)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, aw, h, 5, fill=0, stroke=1)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(NAVY)
        c.drawString(10, h - 5.5 * mm, f"◆  {self._label}")
        self._para.drawOn(c, 10, 4.5 * mm)


# =============================================================================
# BLOCK PARSER
# =============================================================================

T_H1       = "h1"
T_H2       = "h2"
T_BULLET   = "bullet"
T_NUMBERED = "numbered"
T_DIVIDER  = "divider"
T_QUOTE    = "quote"
T_CALLOUT  = "callout"
T_BODY     = "body"

_CALLOUT_RE = re.compile(
    r'^(key insight|pro tip|note|important|warning|tip|remember)[:\s]',
    re.IGNORECASE,
)


def _classify(raw: str) -> Tuple[str, str]:
    line = raw.strip()
    if not line:
        return (T_BODY, "")

    if re.match(r'^[\*\-_]{1,3}$', line):
        return (T_DIVIDER, "")

    m = re.match(r'^>\s*(.+)$', line)
    if m:
        return (T_QUOTE, m.group(1).strip())

    m2 = _CALLOUT_RE.match(line)
    if m2:
        label = m2.group(1)
        rest  = line[m2.end():].strip()
        return (T_CALLOUT, f"{label}||{rest}")

    # ## Heading (1-6 hashes)
    m = re.match(r'^#{1,6}\s+(.+)$', line)
    if m:
        return (T_H1, m.group(1).strip())

    # **Bold heading** standalone
    m = re.match(r'^\*{2}(.+?)\*{2}$', line)
    if m:
        inner = m.group(1).strip()
        if inner and len(inner.split()) <= 16:
            return (T_H1, inner)

    m = re.match(r'^[\*\-•]\s+(.+)$', line)
    if m:
        return (T_BULLET, m.group(1).strip())

    m = re.match(r'^\d+[\.\)]\s+(.+)$', line)
    if m:
        return (T_NUMBERED, m.group(1).strip())

    words = line.split()
    if line.endswith(":") and 1 <= len(words) <= 9:
        return (T_H2, line.rstrip(":").strip())

    if line.isupper() and 2 <= len(words) <= 7 and len(line) > 3:
        return (T_H2, line.title())

    return (T_BODY, line)


def _parse(raw: str) -> List[Tuple[str, str]]:
    out = []
    for chunk in re.split(r'\n{2,}', raw.strip()):
        for line in chunk.splitlines():
            btype, text = _classify(line)
            if btype == T_DIVIDER:
                out.append((T_DIVIDER, ""))
            elif text:
                out.append((btype, text))
    return out


# =============================================================================
# DROP-CAP
# =============================================================================

def _drop_cap(text: str, styles: dict) -> List:
    if not text:
        return []
    cap_style = ParagraphStyle(
        "DropCap",
        fontName=F_SERIF_BOLD,
        fontSize=44,
        leading=44,
        textColor=INDIGO,
    )
    cap_para  = Paragraph(_esc(text[0]), cap_style)
    rest_para = _safe_para(_inline_md(text[1:]), styles["body"])
    cap_w  = 20 * mm
    rest_w = TW - cap_w - 2 * mm
    t = Table([[cap_para, rest_para]], colWidths=[cap_w, rest_w])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (0, 0),   0),
        ("RIGHTPADDING",  (0, 0), (0, 0),   4),
        ("LEFTPADDING",   (1, 0), (1, 0),   0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [t, Spacer(1, 5 * mm)]


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
        bundle_name: str = "",
    ) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        collector = _PageCollector()

        doc = BaseDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=ML, rightMargin=MR,
            topMargin=MT + 6 * mm,
            bottomMargin=MB,
        )
        doc.ebook_title        = title[:58]
        doc._cover_title       = title
        doc._cover_subtitle    = subtitle
        doc._cover_n_chaps     = len(chapters)
        doc._cover_bundle_name = bundle_name
        doc._current_chapter   = ""
        doc._opener_num        = 1
        doc._opener_title      = ""

        body_frame = RLFrame(ML, MB, TW, PAGE_H - MT - MB - 6 * mm, id="body")

        doc.addPageTemplates([
            PageTemplate(id="Cover",  frames=[body_frame], onPage=_cover_cb),
            PageTemplate(id="Toc",    frames=[body_frame], onPage=_toc_cb),
            PageTemplate(id="Opener", frames=[body_frame], onPage=_opener_cb),
            PageTemplate(id="Body",   frames=[body_frame], onPage=_body_cb),
        ])

        styles = self._styles()
        story  = []

        # ── Cover ─────────────────────────────────────────────────────────────
        story.append(_CoverPlaceholder())
        story.append(NextPageTemplate("Toc"))
        story.append(PageBreak())

        # ── TOC (no page number on TOC pages) ─────────────────────────────────
        story += self._build_toc(chapters, collector)
        story.append(NextPageTemplate("Body"))
        story.append(PageBreak())

        # ── Chapters ──────────────────────────────────────────────────────────
        for i, chap in enumerate(chapters, 1):
            story += self._build_chapter(
                i, len(chapters), chap["title"], chap["content"],
                styles, doc, collector,
            )
            story.append(PageBreak())

        doc.multiBuild(story)
        return output_path

    # =========================================================================
    # TOC
    # =========================================================================

    def _build_toc(self, chapters: List[Dict], collector: _PageCollector) -> list:
        out = [_TocHeader(), Spacer(1, 8 * mm)]
        for i, chap in enumerate(chapters, 1):
            out.append(_TocRow(i, chap["title"], collector))
        return out

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
        doc,
        collector: _PageCollector,
    ) -> list:
        doc._current_chapter = title
        doc._opener_num      = num
        doc._opener_title    = title

        out = []

        # ── Full dark opener page ─────────────────────────────────────────────
        out.append(NextPageTemplate("Opener"))
        out.append(PageBreak())
        out.append(_OpenerPlaceholder())
        out.append(NextPageTemplate("Body"))
        out.append(PageBreak())

        # ── Chapter anchor (for TOC page numbers + PDF bookmark) ─────────────
        out.append(_ChapterAnchor(num, collector))

        # ── Chapter body ─────────────────────────────────────────────────────
        blocks  = _parse(content)
        pending = []
        is_first = True

        def flush():
            if pending:
                out.append(KeepTogether(pending[:]))
                pending.clear()

        for btype, text in blocks:

            if btype == T_DIVIDER:
                flush()
                out.append(Spacer(1, 2 * mm))
                out.append(_SectionDivider())
                out.append(Spacer(1, 3 * mm))

            elif btype == T_H1:
                flush()
                out.append(Spacer(1, 6 * mm))
                out.append(_H1Bar(text))
                out.append(Spacer(1, 3.5 * mm))

            elif btype == T_H2:
                flush()
                out.append(Spacer(1, 3 * mm))
                pending.append(_safe_para(_inline_md(text), styles["h2"]))
                pending.append(Spacer(1, 2 * mm))

            elif btype in (T_BULLET, T_NUMBERED):
                icon = "▸" if btype == T_BULLET else "◆"
                pending.append(_safe_para(
                    f'<font color="#4A5BE0" size="9">{icon}</font>  {_inline_md(text)}',
                    styles["bullet"],
                ))
                pending.append(Spacer(1, 1.5 * mm))

            elif btype == T_QUOTE:
                flush()
                out.append(Spacer(1, 2.5 * mm))
                out.append(_PullQuote(text, styles["quote"]))
                out.append(Spacer(1, 2.5 * mm))

            elif btype == T_CALLOUT:
                flush()
                parts = text.split("||", 1)
                label = parts[0] if parts else "Note"
                body  = parts[1] if len(parts) > 1 else text
                out.append(Spacer(1, 2.5 * mm))
                out.append(_CalloutBox(label, body, styles["callout"]))
                out.append(Spacer(1, 2.5 * mm))

            else:  # T_BODY
                flush()
                if is_first:
                    out += _drop_cap(text, styles)
                    is_first = False
                else:
                    out.append(_safe_para(_inline_md(text), styles["body"]))
                    out.append(Spacer(1, 4 * mm))

        flush()
        return out

    # =========================================================================
    # STYLES
    # =========================================================================

    def _styles(self) -> dict:
        return {
            "body": ParagraphStyle(
                "Body",
                fontName=F_SERIF,
                fontSize=11,
                leading=16.5,         # 1.5 × 11
                spaceBefore=0,
                spaceAfter=6,
                textColor=BODY_CLR,
                alignment=TA_JUSTIFY,
            ),
            "h2": ParagraphStyle(
                "H2",
                fontName=F_SERIF_BOLD,
                fontSize=12,
                leading=16,
                spaceAfter=4,
                textColor=H2_CLR,
            ),
            "bullet": ParagraphStyle(
                "Bullet",
                fontName=F_SERIF,
                fontSize=11,
                leading=16,
                spaceAfter=3,
                textColor=BODY_CLR,
                leftIndent=10,
            ),
            "quote": ParagraphStyle(
                "Quote",
                fontName=F_SERIF_ITAL,
                fontSize=11,
                leading=17,
                textColor=HexColor("#2C3A6B"),
            ),
            "callout": ParagraphStyle(
                "Callout",
                fontName=F_SERIF,
                fontSize=10.5,
                leading=16,
                textColor=HexColor("#3A2800"),
            ),
        }

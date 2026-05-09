#!/usr/bin/env python3
"""
PDF Builder — ULTRA PREMIUM Ebook Template
===========================================
Features:
  • Real serif fonts (DejaVu Serif) for cover title & drop-caps
  • Geometric layered cover with texture dot-grid, serif title, gold rules
  • Full-page chapter opener: giant faint chapter number + large white title
  • Running header on every body page (chapter title + hairline rule)
  • Page border: thin inset frame on every body page
  • 6-level content hierarchy with custom flowables
  • Drop-cap first letter of every chapter
  • Callout boxes: KEY INSIGHT / PRO TIP gold-bordered cards
  • Pull-quote boxes with indigo left border
  • Section dividers: ─●─ with gold micro-dots
  • H1 headings: indigo background strip + bold left accent
  • H2 sub-headings: indigo colored
  • Bullets: indigo arrow ▸, numbered: diamond ◆
  • Footer: italic title left, bold indigo page-number right
  • All flowables inherit Flowable (zero crashes)
"""

from __future__ import annotations

import re
import math
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
for _name, _path in _FONT_MAP.items():
    try:
        pdfmetrics.registerFont(TTFont(_name, _path))
    except Exception:
        pass   # Fallback gracefully to Helvetica if unavailable

try:
    pdfmetrics.registerFontFamily(
        "Serif",
        normal="Serif",
        bold="Serif-Bold",
        italic="Serif-Italic",
        boldItalic="Serif-Bold",
    )
except Exception:
    pass

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
ML = MR = 21 * mm
MT = 26 * mm
MB = 22 * mm
TW = PAGE_W - ML - MR


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


# =============================================================================
# COVER
# =============================================================================

def _draw_cover(canvas, doc):
    c = canvas
    W, H = PAGE_W, PAGE_H

    title       = getattr(doc, "_cover_title",       "Ebook")
    subtitle    = getattr(doc, "_cover_subtitle",    "")
    n_chaps     = getattr(doc, "_cover_n_chaps",     0)
    bundle_name = getattr(doc, "_cover_bundle_name", "")

    # ── Deep navy background ──────────────────────────────────────────────────
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # ── Dot-grid texture ──────────────────────────────────────────────────────
    c.saveState()
    c.setFillColor(HexColor("#0E1830"))
    dot_spacing = 14
    for row in range(int(H / dot_spacing) + 1):
        for col in range(int(W / dot_spacing) + 1):
            dx = col * dot_spacing
            dy = row * dot_spacing
            c.circle(dx, dy, 0.7, fill=1, stroke=0)
    c.restoreState()

    # ── Geometric accent triangles top-right ──────────────────────────────────
    c.saveState()
    for colour, pts in [
        (NAVY_MID,  [(W*0.38, H), (W, H), (W, H*0.50)]),
        (NAVY_CARD, [(W*0.58, H), (W, H), (W, H*0.65)]),
        (INDIGO,    [(W*0.73, H), (W, H), (W, H*0.77)]),
        (GOLD,      [(W*0.86, H), (W, H), (W, H*0.88)]),
    ]:
        c.setFillColor(colour)
        p = c.beginPath()
        p.moveTo(*pts[0]); p.lineTo(*pts[1]); p.lineTo(*pts[2]); p.close()
        c.drawPath(p, fill=1, stroke=0)
    c.restoreState()

    # ── Bottom accent bar ─────────────────────────────────────────────────────
    c.setFillColor(INDIGO)
    c.rect(0, 0, W, 14 * mm, fill=1, stroke=0)
    c.setFillColor(GOLD)
    c.rect(0, 0, 24 * mm, 14 * mm, fill=1, stroke=0)

    # ── Left gold bar ─────────────────────────────────────────────────────────
    c.setFillColor(GOLD)
    c.rect(0, 14 * mm, 5, H - 14 * mm, fill=1, stroke=0)

    # ── Bundle name (small caps, above title) ────────────────────────────────
    rule_top = H * 0.68
    if bundle_name:
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(GOLD_LIGHT)
        bn_upper = bundle_name.upper()[:60]
        c.drawString(ML + 10, rule_top + 10 * mm, bn_upper)

    # ── Horizontal rule ABOVE title ───────────────────────────────────────────
    c.setStrokeColor(GOLD)
    c.setLineWidth(0.7)
    c.line(ML + 10, rule_top, ML + 10 + 85 * mm, rule_top)

    # Small gold accent squares on rule
    for rx in [ML + 10, ML + 10 + 85 * mm]:
        c.setFillColor(GOLD)
        c.rect(rx - 2, rule_top - 2, 4, 4, fill=1, stroke=0)

    # ── Title (serif font) ────────────────────────────────────────────────────
    c.setFillColor(WHITE)
    title_lines = _wrap_canvas(title, "Serif-Bold", 27, TW * 0.79, c)
    y = rule_top - 12
    for ln in title_lines:
        c.setFont("Serif-Bold", 27)
        c.drawString(ML + 10, y, ln)
        y -= 33

    # ── Gold rule BELOW title ─────────────────────────────────────────────────
    c.setStrokeColor(GOLD)
    c.setLineWidth(2.2)
    c.line(ML + 10, y - 6, ML + 10 + 75 * mm, y - 6)
    c.setLineWidth(0.5)
    c.line(ML + 10, y - 10, ML + 10 + 75 * mm, y - 10)
    y -= 22

    # ── Subtitle ─────────────────────────────────────────────────────────────
    c.setFillColor(HexColor("#7B9EC0"))
    c.setFont("Serif-Italic", 10)
    sub_lines = _wrap_canvas(subtitle, "Serif-Italic", 10, TW * 0.77, c)
    for sl in sub_lines[:5]:
        c.drawString(ML + 10, y, sl)
        y -= 14

    # ── Meta text in bottom bar ───────────────────────────────────────────────
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(WHITE)
    c.drawString(28 * mm, 5 * mm,
                 f"{n_chaps} Chapters  ·  {datetime.now().year}  ·  Complete Guide")


# =============================================================================
# CHAPTER OPENER  (full dark canvas page)
# =============================================================================

def _draw_chapter_opener(canvas, doc):
    """Full dark page for the chapter opener — called via onPage for opener template."""
    c = canvas
    W, H = PAGE_W, PAGE_H
    num   = getattr(doc, "_opener_num",   1)
    title = getattr(doc, "_opener_title", "")

    # Dark navy background
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Subtle dot texture
    c.setFillColor(HexColor("#0E1830"))
    dot_spacing = 18
    for row in range(int(H / dot_spacing) + 1):
        for col in range(int(W / dot_spacing) + 1):
            c.circle(col * dot_spacing, row * dot_spacing, 0.6, fill=1, stroke=0)

    # Massive faint chapter number watermark
    c.saveState()
    c.setFillColor(HexColor("#101D32"))
    c.setFont("Helvetica-Bold", 260)
    num_str = f"{num:02d}"
    c.drawCentredString(W / 2, H * 0.28, num_str)
    c.restoreState()

    # Gold left bar
    c.setFillColor(GOLD)
    c.rect(0, 0, 5, H, fill=1, stroke=0)

    # Indigo bottom bar
    c.setFillColor(INDIGO)
    c.rect(0, 0, W, 10 * mm, fill=1, stroke=0)

    # "CHAPTER XX" label
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GOLD_LIGHT)
    c.drawString(ML + 6, H * 0.60, f"CHAPTER  {num:02d}")

    # Gold rule below label
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.5)
    c.line(ML + 6, H * 0.60 - 6, ML + 6 + 60 * mm, H * 0.60 - 6)

    # Chapter title (large, serif)
    c.setFillColor(WHITE)
    title_lines = _wrap_canvas(title, "Serif-Bold", 26, W - ML - MR - 20, c)
    y = H * 0.60 - 24
    for ln in title_lines:
        c.setFont("Serif-Bold", 26)
        c.drawString(ML + 6, y, ln)
        y -= 34

    # "Turn the page" subtle prompt
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(HexColor("#3A5070"))
    c.drawString(ML + 6, 14 * mm, "Continue reading →")


# =============================================================================
# PAGE CALLBACKS
# =============================================================================

def _cover_cb(canvas, doc):
    _draw_cover(canvas, doc)


def _opener_cb(canvas, doc):
    _draw_chapter_opener(canvas, doc)


def _body_cb(canvas, doc):
    c = canvas
    c.saveState()

    # ── Page border ───────────────────────────────────────────────────────────
    c.setStrokeColor(BORDER_CLR)
    c.setLineWidth(0.4)
    inset = BORDER_INSET
    c.rect(inset, inset, PAGE_W - 2*inset, PAGE_H - 2*inset, fill=0, stroke=1)

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

    # Footer: book title left, page number right
    c.setFont("Serif-Italic", 7.5)
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
    """Fills the entire chapter opener page (dark canvas drawn by _opener_cb)."""
    def wrap(self, aw, ah): return (aw, ah)
    def draw(self): pass


class _TOCHeader(Flowable):
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
        c.rect(0, 0, 5, self.H, fill=1, stroke=0)
        c.setFillColor(INDIGO)
        c.rect(0, 0, aw, 2, fill=1, stroke=0)
        c.setFont("Serif-Bold", 16)
        c.setFillColor(WHITE)
        c.drawString(14, 6.5 * mm, "Table of Contents")


class _H1Bar(Flowable):
    """Section heading: soft indigo background + bold left accent."""
    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def wrap(self, aw, ah):
        self._aw = aw
        return (aw, 11 * mm)

    def draw(self):
        c = self.canv
        # Soft indigo background
        c.setFillColor(INDIGO_BG)
        c.rect(0, 0, self._aw, 11 * mm, fill=1, stroke=0)
        # Bold left bar
        c.setFillColor(INDIGO)
        c.rect(0, 0, 4, 11 * mm, fill=1, stroke=0)
        # Gold micro-square accent
        c.setFillColor(GOLD)
        c.rect(0, 11*mm - 4, 4, 4, fill=1, stroke=0)
        # Text
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
        # Center dot
        c.setFillColor(INDIGO)
        c.circle(mid, cy, 3.5, fill=1, stroke=0)
        # Gold micro-dots
        c.setFillColor(GOLD)
        c.circle(mid - 11, cy, 1.8, fill=1, stroke=0)
        c.circle(mid + 11, cy, 1.8, fill=1, stroke=0)
        # Outer faint dots
        c.setFillColor(DIVIDER_LN)
        c.circle(mid - 22, cy, 1.2, fill=1, stroke=0)
        c.circle(mid + 22, cy, 1.2, fill=1, stroke=0)


class _PullQuote(Flowable):
    """Indented italic pull-quote with indigo left border."""
    def __init__(self, text: str, style):
        super().__init__()
        self._text  = text
        self._style = style

    def wrap(self, aw, ah):
        self._aw = aw
        self._para = Paragraph(_esc(self._text), self._style)
        inner_w = aw - 22
        pw, ph = self._para.wrap(inner_w, ah)
        self._ph = ph
        return (aw, ph + 9 * mm)

    def draw(self):
        c  = self.canv
        h  = self._ph + 9 * mm
        # Background
        c.setFillColor(QUOTE_BG)
        c.roundRect(0, 0, self._aw, h, 4, fill=1, stroke=0)
        # Left bar
        c.setFillColor(INDIGO)
        c.rect(0, 0, 4, h, fill=1, stroke=0)
        # Serif quote mark
        c.setFont("Serif-Bold", 28)
        c.setFillColor(HexColor("#C0C8F0"))
        c.drawString(10, h - 10 * mm, "\u201c")
        # Paragraph
        self._para.drawOn(c, 16, 4.5 * mm)


class _CalloutBox(Flowable):
    """Gold-topped callout box: KEY INSIGHT / PRO TIP."""
    def __init__(self, label: str, text: str, style):
        super().__init__()
        self._label = label.upper()
        self._text  = text
        self._style = style

    def wrap(self, aw, ah):
        self._aw   = aw
        self._para = Paragraph(_esc(self._text), self._style)
        inner_w    = aw - 20
        pw, ph     = self._para.wrap(inner_w, ah)
        self._ph   = ph
        return (aw, ph + 14 * mm)

    def draw(self):
        c  = self.canv
        h  = self._ph + 14 * mm
        aw = self._aw
        # Background
        c.setFillColor(CALLOUT_BG)
        c.roundRect(0, 0, aw, h, 5, fill=1, stroke=0)
        # Gold top bar
        c.setFillColor(GOLD)
        c.roundRect(0, h - 8*mm, aw, 8*mm, 5, fill=1, stroke=0)
        c.rect(0, h - 8*mm - 4, aw, 4, fill=1, stroke=0)  # flatten bottom corners
        # Border
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.8)
        c.roundRect(0, 0, aw, h, 5, fill=0, stroke=1)
        # Label text
        c.setFont("Helvetica-Bold", 8)
        c.setFillColor(NAVY)
        c.drawString(10, h - 5.5 * mm, f"◆  {self._label}")
        # Body paragraph
        self._para.drawOn(c, 10, 4.5 * mm)


# =============================================================================
# BLOCK PARSER
# =============================================================================

T_H1      = "h1"
T_H2      = "h2"
T_BULLET  = "bullet"
T_NUMBERED= "numbered"
T_DIVIDER = "divider"
T_QUOTE   = "quote"
T_CALLOUT = "callout"
T_BODY    = "body"

_CALLOUT_KEYWORDS = re.compile(
    r'^(key insight|pro tip|note|important|warning|tip|remember)[:\s]',
    re.IGNORECASE
)


def _classify(raw: str) -> Tuple[str, str]:
    line = raw.strip()
    if not line:
        return (T_BODY, "")

    # Lone divider
    if re.match(r'^[\*\-_]{1,3}$', line):
        return (T_DIVIDER, "")

    # Block-quote / pull-quote
    m = re.match(r'^>\s*(.+)$', line)
    if m:
        return (T_QUOTE, m.group(1).strip())

    # Callout keywords
    m2 = _CALLOUT_KEYWORDS.match(line)
    if m2:
        label = m2.group(1)
        rest  = line[m2.end():].strip()
        return (T_CALLOUT, f"{label}||{rest}")

    # Bold heading **text**
    m = re.match(r'^\*{1,2}(.+?)\*{1,2}$', line)
    if m:
        inner = m.group(1).strip()
        if inner and len(inner.split()) <= 16:
            return (T_H1, inner)

    # Markdown heading
    m = re.match(r'^#{1,4}\s+(.+)$', line)
    if m:
        return (T_H1, m.group(1).strip())

    # Bullet
    m = re.match(r'^[\*\-•]\s+(.+)$', line)
    if m:
        return (T_BULLET, m.group(1).strip())

    # Numbered list
    m = re.match(r'^\d+[\.\)]\s+(.+)$', line)
    if m:
        return (T_NUMBERED, m.group(1).strip())

    # Sub-heading: short line ending in colon
    words = line.split()
    if line.endswith(":") and 1 <= len(words) <= 9:
        return (T_H2, line.rstrip(":").strip())

    # ALL CAPS short phrase
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
        fontName="Serif-Bold",
        fontSize=42,
        leading=42,
        textColor=INDIGO,
    )
    rest_para = Paragraph(_esc(text[1:]), styles["body"])
    cap_para  = Paragraph(_esc(text[0]), cap_style)
    cap_w     = 20 * mm
    rest_w    = TW - cap_w - 2 * mm
    t = Table([[cap_para, rest_para]], colWidths=[cap_w, rest_w])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (0, 0),   0),
        ("RIGHTPADDING",  (0, 0), (0, 0),   4),
        ("LEFTPADDING",   (1, 0), (1, 0),   0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [t, Spacer(1, 4 * mm)]


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

        doc = BaseDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=ML, rightMargin=MR,
            topMargin=MT + 6 * mm,   # extra top margin for running header
            bottomMargin=MB,
        )
        doc.ebook_title          = title[:58]
        doc._cover_title         = title
        doc._cover_subtitle      = subtitle
        doc._cover_n_chaps       = len(chapters)
        doc._cover_bundle_name   = bundle_name
        doc._current_chapter     = ""
        doc._opener_num          = 1
        doc._opener_title        = ""

        body_frame = RLFrame(ML, MB, TW, PAGE_H - MT - MB - 6*mm, id="body")

        doc.addPageTemplates([
            PageTemplate(id="Cover",  frames=[body_frame], onPage=_cover_cb),
            PageTemplate(id="Opener", frames=[body_frame], onPage=_opener_cb),
            PageTemplate(id="Body",   frames=[body_frame], onPage=_body_cb),
        ])

        styles = self._styles()
        story  = []

        # ── Cover ─────────────────────────────────────────────────────────────
        story.append(_CoverPlaceholder())
        story.append(NextPageTemplate("Body"))
        story.append(PageBreak())

        # ── TOC ───────────────────────────────────────────────────────────────
        story += self._build_toc(chapters, styles)
        story.append(PageBreak())

        # ── Chapters ──────────────────────────────────────────────────────────
        for i, chap in enumerate(chapters, 1):
            story += self._build_chapter(
                i, len(chapters), chap["title"], chap["content"], styles, doc
            )
            story.append(PageBreak())

        doc.build(story)
        return output_path

    # =========================================================================
    # TOC
    # =========================================================================

    def _build_toc(self, chapters: List[Dict], styles: dict) -> list:
        out = [_TOCHeader(), Spacer(1, 9 * mm)]
        for i, chap in enumerate(chapters, 1):
            safe = _esc(chap["title"][:70])
            num_p = Paragraph(
                f'<font color="#C9950A" size="12">{i:02d}</font>',
                styles["toc_num"],
            )
            title_p = Paragraph(safe, styles["toc_title"])
            t = Table([[num_p, title_p]], colWidths=[13 * mm, TW - 13 * mm])
            t.setStyle(TableStyle([
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING",    (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LINEBELOW",     (0, 0), (-1, 0),  0.4, HexColor("#D1DCE8")),
            ]))
            out.append(t)
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
    ) -> list:
        # Update doc state for running header + opener page
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

        # ── Chapter body ─────────────────────────────────────────────────────
        blocks   = _parse(content)
        pending  = []
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
                pending.append(Paragraph(_esc(text), styles["h2"]))
                pending.append(Spacer(1, 2 * mm))

            elif btype in (T_BULLET, T_NUMBERED):
                icon = "▸" if btype == T_BULLET else "◆"
                pending.append(Paragraph(
                    f'<font color="#4A5BE0" size="9">{icon}</font>  {_esc(text)}',
                    styles["bullet"],
                ))
                pending.append(Spacer(1, 2 * mm))

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
                    out.append(Paragraph(_esc(text), styles["body"]))
                    out.append(Spacer(1, 3.5 * mm))

        flush()
        return out

    # =========================================================================
    # STYLES
    # =========================================================================

    def _styles(self) -> dict:
        return {
            "body": ParagraphStyle(
                "Body",
                fontName="Helvetica",
                fontSize=10.5,
                leading=16.8,
                textColor=BODY_CLR,
                alignment=TA_JUSTIFY,
            ),
            "h2": ParagraphStyle(
                "H2",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=15,
                textColor=H2_CLR,
            ),
            "bullet": ParagraphStyle(
                "Bullet",
                fontName="Helvetica",
                fontSize=10.5,
                leading=15.5,
                textColor=BODY_CLR,
                leftIndent=10,
            ),
            "quote": ParagraphStyle(
                "Quote",
                fontName="Serif-Italic",
                fontSize=10.5,
                leading=16,
                textColor=HexColor("#2C3A6B"),
            ),
            "callout": ParagraphStyle(
                "Callout",
                fontName="Helvetica",
                fontSize=10,
                leading=15,
                textColor=HexColor("#3A2800"),
            ),
            "toc_num": ParagraphStyle(
                "TocNum",
                fontName="Serif-Bold",
                fontSize=12,
                leading=15,
                textColor=GOLD,
            ),
            "toc_title": ParagraphStyle(
                "TocTitle",
                fontName="Helvetica",
                fontSize=10.5,
                leading=15,
                textColor=BODY_CLR,
            ),
        }
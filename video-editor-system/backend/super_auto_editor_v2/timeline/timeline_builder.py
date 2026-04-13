from __future__ import annotations

"""
timeline_builder.py
-------------------
Generates video timelines using cycle math:

  Cycle = Avatar 20s + Media 15s = 35s per cycle
  Avatar segment ≈ 40 words  (20s at 120 wpm)
  Media segment  = 15s  (B-roll overlay over avatar)

  Script math example (300 words):
    Word count     : 300
    Duration       : 150.0s  (2.50 min)
    Cycles (÷35)   : 4
    Avatar total   : 80s  (4 × 20s)
    Media total    : 60s  (4 × 15s)
    Avatar segments: 4   (~40 words each)
    Media segments : 4   (15s each)

The timeline is built directly from the script text — no external JSON required
(JSON loading kept for backward compatibility).
"""

import json
import re
from pathlib import Path

from super_auto_editor_v2.models import TimelineBlock


class TimelineBuilder:
    # ------- Cycle constants -------
    WPM: int = 120           # words per minute (normal speech pace)
    AVATAR_SECONDS: int = 20 # duration of each avatar window
    MEDIA_SECONDS: int = 15  # duration of each media overlay window
    CYCLE_SECONDS: int = AVATAR_SECONDS + MEDIA_SECONDS  # 35s

    @property
    def words_per_avatar(self) -> int:
        """Target word count per avatar segment (≈ 40 words)."""
        return int(self.WPM / 60 * self.AVATAR_SECONDS)

    # ------------------------------------------------------------------
    # Primary path: generate timeline from script using cycle math
    # ------------------------------------------------------------------

    def build_from_script(
        self, script_text: str, avatar_duration: float
    ) -> list[TimelineBlock]:
        """
        Auto-generate an alternating avatar+media timeline.

        All math is printed so operators can verify segment counts.
        """
        words = script_text.split()
        word_count = len(words)
        duration_sec = word_count / self.WPM * 60
        cycles = max(1, round(duration_sec / self.CYCLE_SECONDS))

        # ---- Show all math ----
        print(f"[Timeline] ── SCRIPT MATH ──────────────────────────────")
        print(f"[Timeline] Word count     : {word_count}")
        print(f"[Timeline] Duration       : {duration_sec:.1f}s  ({duration_sec/60:.2f} min)")
        print(f"[Timeline] Cycle (35s)    : {word_count}/{self.WPM}wpm ÷ {self.CYCLE_SECONDS}s = {cycles} cycles")
        print(f"[Timeline] Avatar total   : {cycles} × {self.AVATAR_SECONDS}s = {cycles * self.AVATAR_SECONDS}s")
        print(f"[Timeline] Media total    : {cycles} × {self.MEDIA_SECONDS}s  = {cycles * self.MEDIA_SECONDS}s")
        print(f"[Timeline] Avatar segments: {cycles}  (~{self.words_per_avatar} words each)")
        print(f"[Timeline] Media segments : {cycles}  ({self.MEDIA_SECONDS}s each, overlaid on avatar)")
        print(f"[Timeline] ─────────────────────────────────────────────")

        avatar_chunks = self._split_into_chunks(script_text, cycles)

        blocks: list[TimelineBlock] = []
        t = 0.0
        for i, chunk in enumerate(avatar_chunks):
            if t >= avatar_duration:
                break

            # Avatar block
            a_end = min(t + self.AVATAR_SECONDS, avatar_duration)
            blocks.append(TimelineBlock(
                type="avatar",
                start=round(t, 3),
                end=round(a_end, 3),
                script_text=chunk,
            ))
            t = a_end
            if t >= avatar_duration:
                break

            # Media overlay block (B-roll shown during the NEXT avatar window)
            m_end = min(t + self.MEDIA_SECONDS, avatar_duration)
            if m_end > t:
                blocks.append(TimelineBlock(
                    type="media",
                    start=round(t, 3),
                    end=round(m_end, 3),
                    script_text=chunk,  # context for keyword generation
                ))
            t = m_end

        return blocks

    # ------------------------------------------------------------------
    # Legacy path: load from external JSON file
    # ------------------------------------------------------------------

    def load(self, path: Path, script_text: str) -> list[TimelineBlock]:
        """
        Load timeline from a JSON file.
        Backfills script_text onto media blocks if missing.
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        blocks = [
            TimelineBlock(
                type=item["type"],
                start=float(item["start"]),
                end=float(item["end"]),
                script_text=item.get("script_text", ""),
            )
            for item in data
        ]
        media_blocks = [b for b in blocks if b.type == "media"]
        if media_blocks and not any(b.script_text for b in media_blocks):
            chunks = self._split_into_chunks(script_text, len(media_blocks))
            idx = 0
            for block in blocks:
                if block.type == "media":
                    block.script_text = chunks[idx] if idx < len(chunks) else ""
                    idx += 1
        return blocks

    # ------------------------------------------------------------------
    # Script splitting helper
    # ------------------------------------------------------------------

    def _split_into_chunks(self, script_text: str, num_chunks: int) -> list[str]:
        """
        Split script at sentence boundaries into num_chunks pieces.
        Each chunk targets ~words_per_avatar words (never cuts mid-sentence).
        """
        if num_chunks <= 0:
            return []

        sentences = re.split(r"(?<=[.!?])\s+", script_text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [script_text] * num_chunks

        if len(sentences) <= num_chunks:
            return (sentences + [""] * num_chunks)[:num_chunks]

        target_words = self.words_per_avatar
        chunks: list[str] = []
        current: list[str] = []
        current_words = 0

        for sent in sentences:
            current.append(sent)
            current_words += len(sent.split())
            if current_words >= target_words and len(chunks) < num_chunks - 1:
                chunks.append(" ".join(current))
                current = []
                current_words = 0

        if current:
            chunks.append(" ".join(current))

        while len(chunks) < num_chunks:
            chunks.append("")

        return chunks[:num_chunks]

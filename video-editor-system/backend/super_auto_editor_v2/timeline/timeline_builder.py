from __future__ import annotations

"""
timeline_builder.py
-------------------
Video structure:

  0–3s  → HOOK media (global topic, max-impact visual, hook_score 9-10)
  Then repeating cycle until end of avatar video:
    20s avatar  →  20s media  →  10s avatar  →  10s media   (60s per cycle)

  Words per 60s cycle at 120 wpm:
    20s avatar = 40 words
    10s avatar = 20 words
    Total      = 60 words per cycle

  Example (240-word script, 4-min avatar):
    Hook       :  3s  (media, global topic)
    Cycles     :  3   (remaining 237s ÷ 60s ≈ 4 → capped to fit duration)
    Avatar     :  3 × (20 + 10)s = 90s
    Media      :  3s + 3 × (20 + 10)s = 93s
    Avatar segs:  6  (40 / 20 / 40 / 20 / 40 / 20 words)
    Media segs :  7  (1 hook + 6 regular)
"""

import json
import re
from pathlib import Path

from super_auto_editor_v2.models import TimelineBlock


class TimelineBuilder:
    WPM: int = 120          # words per minute (normal speech pace)
    HOOK_SECONDS: int = 3   # opening hook media window

    # Repeating cycle after the hook: (type, duration_seconds)
    CYCLE_PATTERN: tuple[tuple[str, int], ...] = (
        ("avatar", 20),
        ("media",  20),
        ("avatar", 10),
        ("media",  10),
    )
    CYCLE_SECONDS: int = 60  # sum(CYCLE_PATTERN durations)

    def _words_for(self, seconds: int) -> int:
        return int(self.WPM / 60 * seconds)

    # ------------------------------------------------------------------
    # Primary path: generate timeline from script using cycle math
    # ------------------------------------------------------------------

    def build_from_script(
        self, script_text: str, avatar_duration: float
    ) -> list[TimelineBlock]:
        """
        Build: 3s HOOK + repeating [20s avatar, 20s media, 10s avatar, 10s media].
        All math is printed so operators can verify segment counts.
        """
        word_count = len(script_text.split())
        duration_sec = word_count / self.WPM * 60

        usable = max(0.0, avatar_duration - self.HOOK_SECONDS)
        cycles = max(1, round(usable / self.CYCLE_SECONDS))

        # Avatar segment durations: [20, 10] repeated per cycle
        avatar_durations = [d for _, d in self.CYCLE_PATTERN if _ == "avatar"] * cycles

        print(f"[Timeline] ── STRUCTURE ─────────────────────────────────")
        print(f"[Timeline] Word count      : {word_count}")
        print(f"[Timeline] Script duration : {duration_sec:.1f}s  ({duration_sec/60:.2f} min)")
        print(f"[Timeline] Avatar duration : {avatar_duration:.1f}s")
        print(f"[Timeline] Hook            : {self.HOOK_SECONDS}s  (global-topic media)")
        print(f"[Timeline] Cycles          : {cycles}  (60s each: 20+20+10+10)")
        print(f"[Timeline] Avatar segments : {len(avatar_durations)}  {avatar_durations} words each")
        print(f"[Timeline] Media segments  : 1 hook + {cycles*2} regular")
        print(f"[Timeline] ─────────────────────────────────────────────")

        # Split script proportionally to avatar segment durations
        avatar_chunks = self._split_for_durations(script_text, avatar_durations)

        blocks: list[TimelineBlock] = []
        t = 0.0

        # ── HOOK: 0-3s ───────────────────────────────────────────────
        hook_end = min(float(self.HOOK_SECONDS), avatar_duration)
        if hook_end > 0:
            blocks.append(TimelineBlock(
                type="media",
                start=0.0,
                end=round(hook_end, 3),
                script_text=script_text[:600],   # full intro context for hook query
                hook=True,
            ))
        t = hook_end

        # ── Repeating cycle ──────────────────────────────────────────
        chunk_idx = 0
        last_avatar_text = script_text[:300]   # fallback context for first media

        for _ in range(cycles):
            if t >= avatar_duration:
                break
            for block_type, seg_dur in self.CYCLE_PATTERN:
                if t >= avatar_duration:
                    break
                end = min(t + seg_dur, avatar_duration)

                if block_type == "avatar":
                    chunk = avatar_chunks[chunk_idx] if chunk_idx < len(avatar_chunks) else ""
                    chunk_idx += 1
                    last_avatar_text = chunk or last_avatar_text
                    blocks.append(TimelineBlock(
                        type="avatar",
                        start=round(t, 3),
                        end=round(end, 3),
                        script_text=chunk,
                    ))
                else:
                    # Media: use the text of the immediately preceding avatar block
                    blocks.append(TimelineBlock(
                        type="media",
                        start=round(t, 3),
                        end=round(end, 3),
                        script_text=last_avatar_text,
                    ))

                t = end

        return blocks

    # ------------------------------------------------------------------
    # Legacy path: load from external JSON file
    # ------------------------------------------------------------------

    def load(self, path: Path, script_text: str) -> list[TimelineBlock]:
        """Load timeline from a JSON file; backfills script_text on media blocks."""
        data = json.loads(path.read_text(encoding="utf-8"))
        blocks = [
            TimelineBlock(
                type=item["type"],
                start=float(item["start"]),
                end=float(item["end"]),
                script_text=item.get("script_text", ""),
                hook=bool(item.get("hook", False)),
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
    # Script splitting helpers
    # ------------------------------------------------------------------

    def _split_for_durations(
        self, script_text: str, durations: list[int]
    ) -> list[str]:
        """
        Split script into chunks sized proportionally to avatar segment durations.
        Splits only at sentence boundaries — never mid-sentence.
        """
        if not durations:
            return []

        sentences = re.split(r"(?<=[.!?])\s+", script_text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [script_text] * len(durations)

        target_words = [self._words_for(d) for d in durations]
        chunks: list[str] = []
        current: list[str] = []
        current_words = 0
        seg_idx = 0

        for sent in sentences:
            current.append(sent)
            current_words += len(sent.split())
            if seg_idx < len(durations) - 1 and current_words >= target_words[seg_idx]:
                chunks.append(" ".join(current))
                current = []
                current_words = 0
                seg_idx += 1

        if current:
            chunks.append(" ".join(current))

        # Pad / trim to exact length
        while len(chunks) < len(durations):
            chunks.append("")
        return chunks[: len(durations)]

    def _split_into_chunks(self, script_text: str, num_chunks: int) -> list[str]:
        """Legacy equal-split used by load()."""
        if num_chunks <= 0:
            return []
        equal_dur = [20] * num_chunks
        return self._split_for_durations(script_text, equal_dur)

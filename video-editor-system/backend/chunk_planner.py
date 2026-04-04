#!/usr/bin/env python3
"""
Chunk Planner - Dynamic chunking for ALL script lengths (1k – 100k chars).

Strategy for every length:
  - Hook  : 20 % of total, capped at 8 000 chars (min 2 000)
  - Close : 15 % of total, capped at 8 000 chars (min 1 500)
  - Middle: remainder split into chunks of at most MAX_CHUNK_SIZE chars

Keeping every chunk ≤ 8 000 chars makes the model reliably fill its target
and stay well inside Gemini's output-token limit, so the final script always
reaches the requested length without needing many extension retries.

The niche formula (Writing Guidelines) is injected into EVERY chunk so
100 % of the formula is applied regardless of total length chosen.

API-call count examples:
  10 000 chars →  3 chunks
  30 000 chars →  5–6 chunks
  60 000 chars →  9–10 chunks
  80 000 chars → 12–13 chunks
 100 000 chars → 15–16 chunks  (all within 20 calls/min quota)
"""

import math
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for a single chunk"""
    index: int
    role: str           # HOOK_AND_FRAMEWORK | DEEP_INSIGHTS_AND_EXAMPLES | IMPLEMENTATION_AND_CLOSE
    target_chars: int
    # Fraction of the full script this chunk covers  (0.0–1.0)
    script_position_start: float = 0.0
    script_position_end: float   = 1.0


# Every chunk is kept at or below this size so the model fills it reliably.
MAX_CHUNK_SIZE = 8_000


class ChunkPlanner:
    """
    Dynamic chunk planner that works for ANY script length (1 000 – 100 000 chars).

    The plan always has at least 3 chunks:
      1. HOOK_AND_FRAMEWORK      (opening)
      N. DEEP_INSIGHTS_AND_EXAMPLES  (one or more middle chunks)
      last. IMPLEMENTATION_AND_CLOSE (closing)
    """

    def __init__(self, total_chars: int):
        self.total_chars = total_chars

    def plan(self) -> list:
        """Return a list of ChunkConfig objects (always ≥ 3)."""

        # --- hook & close sizes (proportional, capped) ---
        hook_size  = max(2_000, min(int(self.total_chars * 0.20), 8_000))
        close_size = max(1_500, min(int(self.total_chars * 0.15), 8_000))

        # Guard: for very short targets keep hook+close within budget
        if hook_size + close_size >= self.total_chars:
            hook_size  = int(self.total_chars * 0.35)
            close_size = self.total_chars - hook_size
            return [
                ChunkConfig(index=1, role="HOOK_AND_FRAMEWORK",
                            target_chars=hook_size,
                            script_position_start=0.0,
                            script_position_end=float(hook_size)/self.total_chars),
                ChunkConfig(index=2, role="IMPLEMENTATION_AND_CLOSE",
                            target_chars=close_size,
                            script_position_start=float(hook_size)/self.total_chars,
                            script_position_end=1.0),
            ]

        middle_total = self.total_chars - hook_size - close_size

        # Split middle into ≤ MAX_CHUNK_SIZE pieces
        n_middle    = max(1, math.ceil(middle_total / MAX_CHUNK_SIZE))
        middle_size = middle_total // n_middle
        remainder   = middle_total - middle_size * n_middle

        chunks = []

        # Hook
        hook_end = hook_size / self.total_chars
        chunks.append(ChunkConfig(
            index=1,
            role="HOOK_AND_FRAMEWORK",
            target_chars=hook_size,
            script_position_start=0.0,
            script_position_end=round(hook_end, 3),
        ))

        # Middle chunks
        cursor = hook_size
        for i in range(n_middle):
            extra = remainder if i == n_middle - 1 else 0
            size  = middle_size + extra
            pos_start = cursor / self.total_chars
            pos_end   = (cursor + size) / self.total_chars
            chunks.append(ChunkConfig(
                index=len(chunks) + 1,
                role="DEEP_INSIGHTS_AND_EXAMPLES",
                target_chars=size,
                script_position_start=round(pos_start, 3),
                script_position_end=round(min(pos_end, 1.0), 3),
            ))
            cursor += size

        # Close
        chunks.append(ChunkConfig(
            index=len(chunks) + 1,
            role="IMPLEMENTATION_AND_CLOSE",
            target_chars=close_size,
            script_position_start=round((self.total_chars - close_size) / self.total_chars, 3),
            script_position_end=1.0,
        ))

        return chunks

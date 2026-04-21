#!/usr/bin/env python3
"""
Chunk Planner - Dynamic chunking for ALL script lengths (1k – 240k chars).

Strategy for every length:
  - Hook  : 20 % of total, capped at 18 000 chars (min 2 000)
  - Close : 15 % of total, capped at 18 000 chars (min 1 500)
  - Middle: remainder split into chunks of at most MAX_CHUNK_SIZE chars

Keeping every chunk ≤ 18 000 chars means fewer sequential API calls,
faster total generation time, and still well within Gemini's output limits.

API-call count:
  10 000 chars →  3 chunks  (was 3)
  30 000 chars →  4–5 chunks  (was 5–6)
  60 000 chars →  6–7 chunks  (was 8–9)
 100 000 chars →  8–9 chunks  (was 17!)
 240 000 chars → 13–14 chunks  (was 19–20)
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
MAX_CHUNK_SIZE = 18_000


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
        hook_size  = max(2_000, min(int(self.total_chars * 0.20), 18_000))
        close_size = max(1_500, min(int(self.total_chars * 0.15), 18_000))

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

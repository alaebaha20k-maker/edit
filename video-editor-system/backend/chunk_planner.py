#!/usr/bin/env python3
"""
Chunk Planner - Dynamic chunking based on target length
- Small scripts (≤36k chars): 3 chunks (30/40/30 split)
- Large scripts (>36k chars): dynamic chunks targeting ~12k chars each
  so the model reliably fills each chunk without undershooting
"""

import math
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for a single chunk"""
    index: int
    role: str
    target_chars: int


# Maximum characters per chunk — keeps each API call reliable
MAX_CHUNK_SIZE = 12000

# Threshold below which we use the simple 3-chunk split
SMALL_SCRIPT_THRESHOLD = 36000


class ChunkPlanner:
    """
    Dynamic chunk planner.
    - ≤36k chars  → 3 chunks (30/40/30)
    - >36k chars  → hook(10k) + N middle chunks(~12k each) + close(10k)

    This ensures each chunk is small enough that the model reliably
    generates the requested character count, which fixes the length
    mismatch problem for long scripts (60k / 80k).

    API call count:
    - Title generation : 1 call
    - Script chunks    : N calls (3–8 depending on length)
    - Total for 80k    : ~8 calls  (well within 20 calls/min limit)
    """

    def __init__(self, total_chars: int):
        self.total_chars = total_chars

    def plan(self) -> list:
        """
        Plan chunks for the requested total length.

        Returns:
            List of ChunkConfig objects (always ≥ 3)
        """
        if self.total_chars <= SMALL_SCRIPT_THRESHOLD:
            return self._plan_3chunk()
        return self._plan_dynamic()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _plan_3chunk(self) -> list:
        """Classic 30/40/30 split for short scripts."""
        c1 = int(self.total_chars * 0.30)
        c2 = int(self.total_chars * 0.40)
        c3 = self.total_chars - c1 - c2

        return [
            ChunkConfig(index=1, role="HOOK_AND_FRAMEWORK",          target_chars=c1),
            ChunkConfig(index=2, role="DEEP_INSIGHTS_AND_EXAMPLES",  target_chars=c2),
            ChunkConfig(index=3, role="IMPLEMENTATION_AND_CLOSE",    target_chars=c3),
        ]

    def _plan_dynamic(self) -> list:
        """
        Dynamic split for longer scripts.

        Hook  : 10,000 chars (fixed)
        Close : 10,000 chars (fixed)
        Middle: remainder split into ~12k chunks
        """
        hook_size  = 10000
        close_size = 10000
        middle_total = self.total_chars - hook_size - close_size

        # How many middle chunks do we need?
        n_middle = max(1, math.ceil(middle_total / MAX_CHUNK_SIZE))
        middle_size = middle_total // n_middle
        remainder   = middle_total - middle_size * n_middle

        chunks = [
            ChunkConfig(index=1, role="HOOK_AND_FRAMEWORK", target_chars=hook_size)
        ]

        for i in range(n_middle):
            # Give the leftover chars to the last middle chunk
            extra = remainder if i == n_middle - 1 else 0
            chunks.append(ChunkConfig(
                index=len(chunks) + 1,
                role="DEEP_INSIGHTS_AND_EXAMPLES",
                target_chars=middle_size + extra,
            ))

        chunks.append(ChunkConfig(
            index=len(chunks) + 1,
            role="IMPLEMENTATION_AND_CLOSE",
            target_chars=close_size,
        ))

        return chunks

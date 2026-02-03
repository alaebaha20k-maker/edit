#!/usr/bin/env python3
"""
Chunk Planner - ALWAYS returns 3 chunks (30/40/30 split)
This is the PROVEN architecture that avoids rate limits
"""

from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for a single chunk"""
    index: int
    role: str
    target_chars: int


class ChunkPlanner:
    """
    Free-tier planner.
    ALWAYS returns exactly 3 chunks.
    No dynamic chunking.

    This ensures predictable API usage:
    - Title generation: 1 API call
    - Script generation: 3 API calls (one per chunk)
    - Total: 4 API calls per video

    Free tier limit: 20 calls/min
    With 4 calls per video: 5 videos/min maximum
    """

    def __init__(self, total_chars: int):
        self.total_chars = total_chars

    def plan(self) -> list:
        """
        Plan 3 chunks with 30/40/30 split

        Returns:
            List of 3 ChunkConfig objects
        """
        # 30 / 40 / 30 split
        c1 = int(self.total_chars * 0.30)
        c2 = int(self.total_chars * 0.40)
        c3 = self.total_chars - (c1 + c2)

        return [
            ChunkConfig(
                index=1,
                role="HOOK_AND_FRAMEWORK",
                target_chars=c1
            ),
            ChunkConfig(
                index=2,
                role="DEEP_INSIGHTS_AND_EXAMPLES",
                target_chars=c2
            ),
            ChunkConfig(
                index=3,
                role="IMPLEMENTATION_AND_CLOSE",
                target_chars=c3
            )
        ]

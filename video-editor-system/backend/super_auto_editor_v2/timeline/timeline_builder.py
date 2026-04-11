from __future__ import annotations

import json
import re
from pathlib import Path

from super_auto_editor_v2.models import TimelineBlock


class TimelineBuilder:
    def load(self, path: Path, script_text: str) -> list[TimelineBlock]:
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
            chunks = self._split_script_smart(script_text, len(media_blocks))
            idx = 0
            for block in blocks:
                if block.type == "media":
                    block.script_text = chunks[idx] if idx < len(chunks) else ""
                    idx += 1
        return blocks

    def _split_script_smart(self, script_text: str, parts: int) -> list[str]:
        """
        Split script at sentence boundaries instead of arbitrary word counts.

        Strategy:
        1. Split into sentences using punctuation.
        2. Group sentences into `parts` chunks of roughly equal character count.
        3. Each chunk contains complete sentences — never half a sentence.
        """
        if parts <= 0:
            return []

        # Split at sentence-ending punctuation followed by whitespace
        sentences = re.split(r"(?<=[.!?])\s+", script_text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return [""] * parts

        if len(sentences) <= parts:
            # Fewer sentences than requested parts — pad with empty strings
            return sentences + [""] * (parts - len(sentences))

        # Target character count per chunk
        total_chars = sum(len(s) for s in sentences)
        target_chars = total_chars / parts

        chunks: list[str] = []
        current: list[str] = []
        current_chars = 0

        for sent in sentences:
            current.append(sent)
            current_chars += len(sent)

            # Flush when we hit the target AND we still need more chunks
            if current_chars >= target_chars and len(chunks) < parts - 1:
                chunks.append(" ".join(current))
                current = []
                current_chars = 0

        # Remaining sentences go into the last chunk
        if current:
            chunks.append(" ".join(current))

        # Ensure exactly `parts` entries
        while len(chunks) < parts:
            chunks.append("")

        return chunks[:parts]

from __future__ import annotations

import json
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
            chunks = self._split_script(script_text, len(media_blocks))
            idx = 0
            for block in blocks:
                if block.type == "media":
                    block.script_text = chunks[idx]
                    idx += 1
        return blocks

    def _split_script(self, script_text: str, parts: int) -> list[str]:
        words = script_text.split()
        if parts <= 0:
            return []
        size = max(1, len(words) // parts)
        output = []
        for i in range(parts):
            start = i * size
            end = len(words) if i == parts - 1 else (i + 1) * size
            output.append(" ".join(words[start:end]))
        return output

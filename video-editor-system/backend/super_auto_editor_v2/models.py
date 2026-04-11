from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


BlockType = Literal["avatar", "media"]
SceneType = Literal["specific", "general"]
MediaSource = Literal["brave_images", "pexels_video"]


@dataclass(slots=True)
class TimelineBlock:
    type: BlockType
    start: float
    end: float
    script_text: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class SceneAnalysis:
    keywords: list[str]
    named_entities: list[str]
    scene_type: SceneType
    source: MediaSource
    search_queries: list[str]


@dataclass(slots=True)
class ImageCandidate:
    id: str
    url: str
    title: str
    width: int
    height: int
    source: str = "brave"
    score: float = 0.0


@dataclass(slots=True)
class VideoFileVariant:
    url: str
    width: int
    height: int
    fps: float


@dataclass(slots=True)
class VideoCandidate:
    id: str
    duration: float
    width: int
    height: int
    files: list[VideoFileVariant]
    source: str = "pexels"
    score: float = 0.0


@dataclass(slots=True)
class DownloadedAsset:
    scene_id: str
    asset_id: str
    source: str
    query: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RenderProfile:
    preset: str
    crf: int
    audio_codec: str = "aac"


@dataclass(slots=True)
class BuildContext:
    avatar_video: Path
    script_path: Path
    timeline_path: Path
    output_path: Path
    mode: str

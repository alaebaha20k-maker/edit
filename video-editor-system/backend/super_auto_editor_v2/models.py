from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


BlockType = Literal["avatar", "media"]
SceneType = Literal["specific", "general", "mixed"]
MediaSource = Literal["brave_images", "pexels_video", "mixed"]


@dataclass(slots=True)
class TimelineBlock:
    type: BlockType
    start: float
    end: float
    script_text: str = ""
    hook: bool = False   # True for the 0-3s hook media block (global topic, max impact)

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class VisualIntent:
    """Structured description of what needs to be shown visually for a scene."""
    primary_subject: str = ""
    subject_type: str = "concept"   # product | person | place | concept | action
    action: str = ""
    environment: str = ""
    mood: str = ""
    must_show: list[str] = field(default_factory=list)
    must_avoid: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SceneAnalysis:
    keywords: list[str]
    named_entities: list[str]
    scene_type: SceneType
    source: MediaSource
    search_queries: list[str]
    visual_intent: VisualIntent | None = None


@dataclass(slots=True)
class ImageCandidate:
    id: str
    url: str
    title: str
    width: int
    height: int
    source: str = "brave"
    score: float = 0.0
    relevance_score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)


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
    relevance_score: float = 0.0
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DownloadedAsset:
    scene_id: str
    asset_id: str
    source: str
    query: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaPlan:
    """
    Gemini-generated media plan for a single 15s media segment.
    api_choice: "SERPER" | "PEXELS" | "MERGE"
    MERGE = Serper image + Pexels video combined into one clip.
    """
    primary_keyword: str
    fallback_keyword: str
    api_choice: str = "PEXELS"   # default: Pexels video
    serper_keyword: str = ""     # used when api_choice == "MERGE"
    pexels_keyword: str = ""     # used when api_choice == "MERGE"


@dataclass(slots=True)
class RenderProfile:
    preset: str
    crf: int
    audio_codec: str = "aac"
    tune: str = ""   # e.g. "fastdecode" for the turbo profile


@dataclass(slots=True)
class BuildContext:
    avatar_video: Path
    script_path: Path
    timeline_path: Path
    output_path: Path
    mode: str

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass
class ReelMetadata:
    source_url: str
    platform: Literal["instagram", "tiktok", "youtube"]
    author: str | None
    posted_at: datetime | None
    title: str | None
    caption: str | None
    video_path: Path | None = None
    image_paths: list[Path] = field(default_factory=list)
    audio_path: Path | None = None
    hashtags: list[str] = field(default_factory=list)

    def temp_paths(self) -> list[Path]:
        """All locally-downloaded temp files for this reel, for cleanup."""
        paths = list(self.image_paths)
        if self.video_path is not None:
            paths.append(self.video_path)
        if self.audio_path is not None:
            paths.append(self.audio_path)
        return paths


@dataclass
class Item:
    name: str
    item_type: Literal["place", "restaurant", "activity", "tip"]
    description: str


@dataclass
class Ingredient:
    name: str
    quantity: str | None


@dataclass
class TutorialStep:
    step_number: int
    text: str


@dataclass
class ExtractionResult:
    transcription: str
    ocr_text: str
    summary: str
    title: str
    items: list[Item] = field(default_factory=list)
    content_type: Literal["list", "tutorial", "other"] | None = None
    ingredients: list[Ingredient] = field(default_factory=list)
    steps: list[TutorialStep] = field(default_factory=list)

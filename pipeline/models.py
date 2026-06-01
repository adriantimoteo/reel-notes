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
    video_path: Path
    hashtags: list[str] = field(default_factory=list)


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

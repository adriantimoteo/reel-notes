from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ReelMetadata:
    source_url: str
    platform: str                    # "instagram" | "tiktok" | "youtube"
    author: str | None
    posted_at: datetime | None
    title: str | None
    caption: str | None
    video_path: Path
    hashtags: list[str] = field(default_factory=list)


@dataclass
class Item:
    name: str
    item_type: str                   # "place" | "restaurant" | "activity" | "tip"
    description: str


@dataclass
class ExtractionResult:
    transcription: str
    ocr_text: str
    summary: str
    items: list[Item] = field(default_factory=list)

from dataclasses import dataclass, field
from typing import Literal

from reelkit.models import ReelMetadata

__all__ = ["ExtractionResult", "Ingredient", "Item", "ReelMetadata", "TutorialStep"]


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

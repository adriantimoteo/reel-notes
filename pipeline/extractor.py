import logging

import google.genai as genai

import config
from pipeline.models import ExtractionResult, Ingredient, Item, ReelMetadata, TutorialStep
from reelkit import gemini
from reelkit.gemini import MAX_POLL_ATTEMPTS

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-3.5-flash"  # gemini-2.5-flash retires 2026-10-16 — bump this when Google deprecates again

__all__ = ["EXTRACTION_SCHEMA", "MAX_POLL_ATTEMPTS", "MODEL_NAME", "extract", "parse_extraction_response"]

_is_retryable_extraction_error = gemini.is_retryable_error

# Without a timeout a stalled Gemini request hangs the whole run indefinitely. A
# timed-out reel is flagged retryable (see orchestrator._is_transient) and picked
# up by the next run. Normal calls finish in ~20s.
REQUEST_TIMEOUT_MS = 120_000

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=genai.types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
    return _client

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "transcription": {"type": "string"},
        "ocr_text": {"type": "string"},
        "summary": {"type": "string"},
        "content_type": {
            "type": "string",
            "enum": ["list", "tutorial", "other"],
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "item_type": {
                        "type": "string",
                        "enum": ["place", "restaurant", "activity", "tip"],
                    },
                    "description": {"type": "string"},
                },
                "required": ["name", "item_type", "description"],
            },
        },
        "ingredients": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "string"},
                },
                "required": ["name"],
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_number": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["step_number", "text"],
            },
        },
    },
    "required": ["title", "transcription", "ocr_text", "summary", "content_type", "items"],
}


def parse_extraction_response(raw: dict) -> ExtractionResult:
    return ExtractionResult(
        title=raw["title"],
        transcription=raw["transcription"],
        ocr_text=raw["ocr_text"],
        summary=raw["summary"],
        items=[
            Item(
                name=item["name"],
                item_type=item["item_type"],
                description=item["description"],
            )
            for item in raw.get("items", [])
        ],
        content_type=raw.get("content_type"),
        ingredients=[
            Ingredient(
                name=ing["name"],
                quantity=ing.get("quantity"),
            )
            for ing in raw.get("ingredients", [])
        ],
        steps=[
            TutorialStep(
                step_number=step["step_number"],
                text=step["text"],
            )
            for step in raw.get("steps", [])
        ],
    )


def _build_prompt(metadata: ReelMetadata, type_hint: str | None = None) -> str:
    type_hint_block = (
        f"\nOVERRIDE: Treat this reel as type \"{type_hint}\" regardless of content."
        if type_hint is not None
        else ""
    )
    caption_block = f"\nCaption: {metadata.caption}" if metadata.caption else ""
    subject = "these slides from this photo post, in order," if gemini.is_carousel(metadata) else "this video"
    return (
        f"Analyse {subject} and return a structured JSON response.\n"
        "\n"
        "Always extract these fields for every reel:\n"
        "- title: short 3-5 word title describing what the content is about\n"
        "- transcription: verbatim audio transcription (leave empty if there is no audio)\n"
        "- ocr_text: all visible on-screen text\n"
        "- summary: 2-3 sentence summary of the content. Write it directly — do not start with \"This video\", \"This reel\", \"This tutorial\", \"In this video\", or any similar meta-reference to the format.\n"
        "\n"
        "Classify the reel as exactly one of these content types:\n"
        "- \"list\": named recommendations — places, restaurants, food items, products, or tips. "
        "The reel presents a collection of things to visit, try, or use.\n"
        "- \"tutorial\": procedural content — recipes, techniques, workouts, or any reel that walks "
        "through a sequence of steps to accomplish something. The reel explains *how* to do something.\n"
        "- \"other\": everything else — commentary, vlogs, motivational content, storytelling, "
        "or any reel that neither recommends a list of things nor teaches a procedure. "
        "A cooking reel that shows food without clear step-by-step instructions is \"other\", not \"tutorial\".\n"
        "\n"
        "Based on the content type, populate these fields (leave as empty arrays if not applicable):\n"
        "- items: for \"list\" type — the named places, restaurants, activities, or tips mentioned. "
        "Leave empty for \"tutorial\" and \"other\".\n"
        "- ingredients: for \"tutorial\" type — ingredients or materials used, if any are explicitly "
        "shown or stated. Leave empty if none are mentioned or if this is not a cooking/crafting reel.\n"
        "- steps: for \"tutorial\" type — the numbered steps of the procedure, in order. "
        "Leave empty for \"list\" and \"other\".\n"
        "\n"
        "IMPORTANT — no inference: only extract quantities, steps, and item descriptions that are "
        "explicitly shown on screen or said aloud in the reel. Do not guess, infer, or fill in "
        "details that are not directly present."
        f"{type_hint_block}"
        f"{caption_block}"
    )


async def extract(metadata: ReelMetadata, type_hint: str | None = None) -> ExtractionResult:
    raw = await gemini.generate_structured(
        _get_client(),
        MODEL_NAME,
        gemini.media_paths(metadata),
        _build_prompt(metadata, type_hint),
        EXTRACTION_SCHEMA,
        description=f"extraction for {metadata.source_url}",
    )
    logger.info("extraction complete for %s", metadata.source_url)
    return parse_extraction_response(raw)

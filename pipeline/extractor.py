import asyncio
import json
import logging
import time

import google.genai as genai

import config
from pipeline.exceptions import ExtractionError
from pipeline.models import ExtractionResult, Item, ReelMetadata

logger = logging.getLogger(__name__)

MAX_POLL_ATTEMPTS = 30  # 60 seconds total at 2s intervals

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "transcription": {"type": "string"},
        "ocr_text": {"type": "string"},
        "summary": {"type": "string"},
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
    },
    "required": ["title", "transcription", "ocr_text", "summary", "items"],
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
    )


def _extract_sync(metadata: ReelMetadata) -> ExtractionResult:
    client = _get_client()

    video_file = client.files.upload(file=metadata.video_path)
    attempts = 0
    while video_file.state.name == "PROCESSING" and attempts < MAX_POLL_ATTEMPTS:
        time.sleep(2)
        video_file = client.files.get(name=video_file.name)
        attempts += 1

    if video_file.state.name != "ACTIVE":
        raise ExtractionError(
            cause=RuntimeError(f"Gemini file in unexpected state: {video_file.state.name}")
        )

    caption_block = f"\nCaption: {metadata.caption}" if metadata.caption else ""
    prompt = (
        "Analyse this video and return a structured JSON response.\n"
        "Extract:\n"
        "- title: short 3-5 word title describing what the video is about\n"
        "- transcription: verbatim audio transcription\n"
        "- ocr_text: all visible on-screen text\n"
        "- summary: 2-3 sentence summary of what the video is about\n"
        "- items: list of places, restaurants, activities, or tips mentioned"
        f"{caption_block}"
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt],
        config=genai.types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EXTRACTION_SCHEMA,
        ),
    )

    logger.info("extraction complete for %s", metadata.source_url)
    raw = json.loads(response.text)
    return parse_extraction_response(raw)


async def extract(metadata: ReelMetadata) -> ExtractionResult:
    return await asyncio.to_thread(_extract_sync, metadata)

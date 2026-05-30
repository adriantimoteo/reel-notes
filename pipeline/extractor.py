import logging

from pipeline.models import ExtractionResult, Item

logger = logging.getLogger(__name__)

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
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
    "required": ["transcription", "ocr_text", "summary", "items"],
}


def parse_extraction_response(raw: dict) -> ExtractionResult:
    return ExtractionResult(
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

import json
from pathlib import Path

from pipeline.extractor import EXTRACTION_SCHEMA, parse_extraction_response

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "extraction_response.json"


def test_parse_extraction_response_from_fixture() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    result = parse_extraction_response(fixture)

    assert result.transcription == fixture["transcription"]
    assert result.ocr_text == fixture["ocr_text"]
    assert result.summary == fixture["summary"]
    assert len(result.items) == 2
    assert result.items[0].name == "Tonkatsu Maisen Aoyama"
    assert result.items[0].item_type == "restaurant"
    assert result.items[1].name == "Shibuya Sky"
    assert result.items[1].item_type == "place"


def test_parse_extraction_response_empty_items() -> None:
    result = parse_extraction_response(
        {"transcription": "", "ocr_text": "", "summary": "", "items": []}
    )
    assert result.items == []


def test_extraction_schema_top_level_required() -> None:
    assert EXTRACTION_SCHEMA["required"] == ["transcription", "ocr_text", "summary", "items"]


def test_extraction_schema_item_required() -> None:
    assert EXTRACTION_SCHEMA["properties"]["items"]["items"]["required"] == [
        "name",
        "item_type",
        "description",
    ]

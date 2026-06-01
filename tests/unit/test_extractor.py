import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.exceptions import ExtractionError
from pipeline.extractor import EXTRACTION_SCHEMA, MAX_POLL_ATTEMPTS, extract, parse_extraction_response
from pipeline.models import ReelMetadata

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "extraction_response.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text())


def test_parse_extraction_response_from_fixture() -> None:
    fixture = json.loads(FIXTURE_PATH.read_text())
    result = parse_extraction_response(fixture)

    assert result.title == fixture["title"]
    assert result.transcription == fixture["transcription"]
    assert result.ocr_text == fixture["ocr_text"]
    assert result.summary == fixture["summary"]
    assert len(result.items) == 2
    assert result.items[0].name == "Tonkatsu Maisen Aoyama"
    assert result.items[0].item_type == "restaurant"
    assert result.items[1].name == "Shibuya Sky"
    assert result.items[1].item_type == "place"
    assert result.content_type == "list"
    assert result.ingredients == []
    assert result.steps == []


def test_parse_extraction_response_empty_items() -> None:
    result = parse_extraction_response(
        {"title": "", "transcription": "", "ocr_text": "", "summary": "", "items": []}
    )
    assert result.items == []


def test_parse_extraction_response_missing_new_keys_returns_defaults() -> None:
    """Missing content_type, ingredients, steps keys should produce safe defaults."""
    result = parse_extraction_response(
        {"title": "T", "transcription": "t", "ocr_text": "", "summary": "s", "items": []}
    )
    assert result.content_type is None
    assert result.ingredients == []
    assert result.steps == []


def test_parse_extraction_response_tutorial_with_ingredients_and_steps() -> None:
    raw = {
        "title": "Easy Pasta",
        "transcription": "Start by boiling water.",
        "ocr_text": "",
        "summary": "A quick pasta tutorial.",
        "items": [],
        "content_type": "tutorial",
        "ingredients": [
            {"name": "Pasta", "quantity": "200g"},
            {"name": "Salt", "quantity": None},
        ],
        "steps": [
            {"step_number": 1, "text": "Boil water"},
            {"step_number": 2, "text": "Add pasta and cook for 8 minutes"},
        ],
    }
    result = parse_extraction_response(raw)

    assert result.content_type == "tutorial"
    assert len(result.ingredients) == 2
    assert result.ingredients[0].name == "Pasta"
    assert result.ingredients[0].quantity == "200g"
    assert result.ingredients[1].name == "Salt"
    assert result.ingredients[1].quantity is None
    assert len(result.steps) == 2
    assert result.steps[0].step_number == 1
    assert result.steps[0].text == "Boil water"
    assert result.steps[1].step_number == 2
    assert result.steps[1].text == "Add pasta and cook for 8 minutes"


def test_extraction_schema_top_level_required() -> None:
    assert EXTRACTION_SCHEMA["required"] == ["title", "transcription", "ocr_text", "summary", "items"]


def test_extraction_schema_item_required() -> None:
    assert EXTRACTION_SCHEMA["properties"]["items"]["items"]["required"] == [
        "name",
        "item_type",
        "description",
    ]


def _make_metadata(tmp_path: Path, caption: str | None = None) -> tuple[ReelMetadata, Path]:
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake")
    metadata = ReelMetadata(
        source_url="https://youtube.com/shorts/abc",
        platform="youtube",
        author="Chef",
        posted_at=None,
        title="Ramen",
        caption=caption,
        video_path=video_path,
    )
    return metadata, video_path


def _active_upload_mock() -> MagicMock:
    m = MagicMock()
    m.state.name = "ACTIVE"
    return m


@patch("pipeline.extractor._client")
async def test_extract_returns_result(mock_client: MagicMock, tmp_path: Path) -> None:
    mock_client.files.upload.return_value = _active_upload_mock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path)
    result = await extract(metadata)

    assert result.summary == FIXTURE["summary"]


@patch("pipeline.extractor._client")
async def test_files_upload_called_with_video_path(mock_client: MagicMock, tmp_path: Path) -> None:
    mock_client.files.upload.return_value = _active_upload_mock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, video_path = _make_metadata(tmp_path)
    await extract(metadata)

    mock_client.files.upload.assert_called_once_with(file=video_path)


@patch("pipeline.extractor._client")
async def test_generate_content_called_with_correct_model_and_mime(mock_client: MagicMock, tmp_path: Path) -> None:
    mock_client.files.upload.return_value = _active_upload_mock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path)
    await extract(metadata)

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert call_kwargs["config"].response_mime_type == "application/json"


@patch("pipeline.extractor._client")
async def test_caption_included_in_prompt_when_present(mock_client: MagicMock, tmp_path: Path) -> None:
    mock_client.files.upload.return_value = _active_upload_mock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path, caption="Great ramen spot!")
    await extract(metadata)

    prompt = mock_client.models.generate_content.call_args.kwargs["contents"][1]
    assert "Caption:" in prompt


@patch("pipeline.extractor._client")
async def test_no_caption_line_when_caption_is_none(mock_client: MagicMock, tmp_path: Path) -> None:
    mock_client.files.upload.return_value = _active_upload_mock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path, caption=None)
    await extract(metadata)

    prompt = mock_client.models.generate_content.call_args.kwargs["contents"][1]
    assert "Caption:" not in prompt


# --- AC3 & AC4: polling path and FAILED state guard ---

@patch("pipeline.extractor.time.sleep")
@patch("pipeline.extractor._client")
async def test_polling_loop_calls_files_get_until_active(
    mock_client: MagicMock, mock_sleep: MagicMock, tmp_path: Path
) -> None:
    processing = MagicMock()
    processing.state.name = "PROCESSING"
    active = MagicMock()
    active.state.name = "ACTIVE"

    mock_client.files.upload.return_value = processing
    mock_client.files.get.return_value = active
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path)
    await extract(metadata)

    mock_client.files.get.assert_called_once()
    mock_sleep.assert_called_once_with(2)


@patch("pipeline.extractor.time.sleep")
@patch("pipeline.extractor._client")
async def test_failed_state_raises_extraction_error(
    mock_client: MagicMock, mock_sleep: MagicMock, tmp_path: Path
) -> None:
    failed = MagicMock()
    failed.state.name = "FAILED"
    mock_client.files.upload.return_value = failed

    metadata, _ = _make_metadata(tmp_path)
    with pytest.raises(ExtractionError):
        await extract(metadata)


@patch("pipeline.extractor.time.sleep")
@patch("pipeline.extractor._client")
async def test_max_poll_attempts_raises_extraction_error(
    mock_client: MagicMock, mock_sleep: MagicMock, tmp_path: Path
) -> None:
    processing = MagicMock()
    processing.state.name = "PROCESSING"
    mock_client.files.upload.return_value = processing
    mock_client.files.get.return_value = processing

    metadata, _ = _make_metadata(tmp_path)
    with pytest.raises(ExtractionError):
        await extract(metadata)

    assert mock_client.files.get.call_count == MAX_POLL_ATTEMPTS

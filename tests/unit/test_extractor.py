import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from pipeline.extractor import EXTRACTION_SCHEMA, extract, parse_extraction_response
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


def test_parse_extraction_response_empty_items() -> None:
    result = parse_extraction_response(
        {"title": "", "transcription": "", "ocr_text": "", "summary": "", "items": []}
    )
    assert result.items == []


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


@patch("pipeline.extractor.genai.Client")
async def test_extract_returns_result(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = mock_client_cls.return_value
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path)
    result = await extract(metadata)

    assert result.summary == FIXTURE["summary"]


@patch("pipeline.extractor.genai.Client")
async def test_files_upload_called_with_video_path(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = mock_client_cls.return_value
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, video_path = _make_metadata(tmp_path)
    await extract(metadata)

    mock_client.files.upload.assert_called_once_with(file=video_path)


@patch("pipeline.extractor.genai.Client")
async def test_generate_content_called_with_correct_model_and_mime(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = mock_client_cls.return_value
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path)
    await extract(metadata)

    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-flash"
    assert call_kwargs["config"].response_mime_type == "application/json"


@patch("pipeline.extractor.genai.Client")
async def test_caption_included_in_prompt_when_present(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = mock_client_cls.return_value
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path, caption="Great ramen spot!")
    await extract(metadata)

    prompt = mock_client.models.generate_content.call_args.kwargs["contents"][1]
    assert "Caption:" in prompt


@patch("pipeline.extractor.genai.Client")
async def test_no_caption_line_when_caption_is_none(mock_client_cls: MagicMock, tmp_path: Path) -> None:
    mock_client = mock_client_cls.return_value
    mock_client.files.upload.return_value = MagicMock()
    mock_client.models.generate_content.return_value.text = json.dumps(FIXTURE)

    metadata, _ = _make_metadata(tmp_path, caption=None)
    await extract(metadata)

    prompt = mock_client.models.generate_content.call_args.kwargs["contents"][1]
    assert "Caption:" not in prompt

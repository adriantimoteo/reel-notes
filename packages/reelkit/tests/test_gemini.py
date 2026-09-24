"""Unit tests for reelkit/gemini.py — schema-agnostic upload + structured generation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import errors as genai_errors

from reelkit.exceptions import ExtractionError
from reelkit.gemini import (
    MAX_POLL_ATTEMPTS,
    generate_structured,
    is_carousel,
    is_model_retired,
    is_retryable_error,
    media_paths,
)
from reelkit.models import ReelMetadata

SCHEMA = {"type": "object", "properties": {"places": {"type": "array"}}, "required": ["places"]}
RESPONSE = {"places": [{"name": "Shibuya Sky"}]}


def _video_metadata() -> ReelMetadata:
    return ReelMetadata(
        source_url="https://youtube.com/shorts/abc", platform="youtube", author=None,
        posted_at=None, title=None, caption=None, video_path=Path("/tmp/v.mp4"),
    )


def _carousel_metadata(with_audio: bool) -> ReelMetadata:
    return ReelMetadata(
        source_url="https://www.tiktok.com/@u/photo/1", platform="tiktok", author=None,
        posted_at=None, title=None, caption=None,
        image_paths=[Path("/tmp/1.jpg"), Path("/tmp/2.jpg")],
        audio_path=Path("/tmp/a.mp3") if with_audio else None,
    )


def _client(state: str = "ACTIVE") -> MagicMock:
    client = MagicMock()
    client.files.upload.return_value.state.name = state
    client.models.generate_content.return_value.text = json.dumps(RESPONSE)
    return client


# --- media selection ---


def test_media_paths_video() -> None:
    assert media_paths(_video_metadata()) == [Path("/tmp/v.mp4")]
    assert is_carousel(_video_metadata()) is False


def test_media_paths_carousel_with_audio_appends_audio_last() -> None:
    assert media_paths(_carousel_metadata(with_audio=True)) == [
        Path("/tmp/1.jpg"), Path("/tmp/2.jpg"), Path("/tmp/a.mp3"),
    ]
    assert is_carousel(_carousel_metadata(with_audio=True)) is True


def test_media_paths_carousel_without_audio() -> None:
    assert media_paths(_carousel_metadata(with_audio=False)) == [Path("/tmp/1.jpg"), Path("/tmp/2.jpg")]


# --- generate_structured ---


async def test_generate_structured_returns_parsed_json_and_passes_caller_schema() -> None:
    client = _client()
    paths = [Path("/tmp/1.jpg"), Path("/tmp/2.jpg")]

    result = await generate_structured(client, "some-model", paths, "find places", SCHEMA, description="t")

    assert result == RESPONSE
    assert [c.kwargs["file"] for c in client.files.upload.call_args_list] == paths
    kwargs = client.models.generate_content.call_args.kwargs
    assert kwargs["model"] == "some-model"
    assert kwargs["contents"][-1] == "find places"
    assert len(kwargs["contents"]) == 3
    assert kwargs["config"].response_mime_type == "application/json"
    assert kwargs["config"].response_schema == SCHEMA


@patch("reelkit.gemini.time.sleep")
async def test_generate_structured_polls_until_active(mock_sleep: MagicMock) -> None:
    client = _client(state="PROCESSING")
    client.files.get.return_value.state.name = "ACTIVE"

    await generate_structured(client, "m", [Path("/tmp/v.mp4")], "p", SCHEMA, description="t")

    client.files.get.assert_called_once()
    mock_sleep.assert_called_once_with(2)


@patch("reelkit.gemini.time.sleep")
async def test_generate_structured_gives_up_after_max_poll_attempts(mock_sleep: MagicMock) -> None:
    client = _client(state="PROCESSING")
    client.files.get.return_value.state.name = "PROCESSING"

    with pytest.raises(ExtractionError):
        await generate_structured(client, "m", [Path("/tmp/v.mp4")], "p", SCHEMA, description="t")

    assert client.files.get.call_count == MAX_POLL_ATTEMPTS


async def test_generate_structured_failed_upload_raises_extraction_error() -> None:
    with pytest.raises(ExtractionError):
        await generate_structured(_client(state="FAILED"), "m", [Path("/tmp/v.mp4")], "p", SCHEMA, description="t")


async def test_generate_structured_retries_server_error() -> None:
    client = _client()
    active = client.files.upload.return_value
    client.files.upload.side_effect = [genai_errors.ServerError(500, {"message": "boom"}), active]

    with patch("reelkit.retry.asyncio.sleep", AsyncMock()):
        result = await generate_structured(client, "m", [Path("/tmp/v.mp4")], "p", SCHEMA, description="t")

    assert result == RESPONSE
    assert client.files.upload.call_count == 2


# --- error classification ---


def test_is_retryable_error() -> None:
    assert is_retryable_error(genai_errors.ServerError(503, {"message": "x"})) is True
    assert is_retryable_error(genai_errors.ClientError(429, {"message": "x"})) is True
    assert is_retryable_error(genai_errors.ClientError(400, {"message": "x"})) is False
    assert is_retryable_error(genai_errors.ClientError(404, {"message": "x"})) is False
    assert is_retryable_error(RuntimeError("x")) is False


def test_is_model_retired() -> None:
    assert is_model_retired(genai_errors.ClientError(404, {"message": "model gone"})) is True
    assert is_model_retired(genai_errors.ClientError(400, {"message": "x"})) is False
    assert is_model_retired(genai_errors.ServerError(500, {"message": "x"})) is False
    assert is_model_retired(RuntimeError("404")) is False

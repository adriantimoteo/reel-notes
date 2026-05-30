"""Phase 4 integration tests: extractor wired into orchestrator."""

import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import handle_message
from bot.status import StatusMessage
from pipeline.models import ExtractionResult, Item, ReelMetadata
from storage.db import get_connection, init_db
from storage.repository import find_by_url


def _make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    init_db(db_path)
    return get_connection(db_path)


def _make_bot() -> MagicMock:
    bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 1
    bot.send_message = AsyncMock(return_value=sent_msg)
    bot.edit_message_text = AsyncMock()
    return bot


def _make_message(user_id: int, text: str) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.text = text
    message.chat = MagicMock()
    message.chat.id = 100
    return message


ALLOWED_ID = 12345
REEL_URL = "https://instagram.com/reel/p4test1"

EXTRACTION = ExtractionResult(
    transcription="full transcription text",
    ocr_text="visible on-screen text",
    summary="A short summary of the reel content for phase four testing.",
    items=[
        Item(name="Tokyo Ramen", item_type="restaurant", description="Great ramen spot."),
        Item(name="Shibuya Crossing", item_type="place", description="Famous crossing."),
    ],
)


def _make_fetch_result(video_path: Path) -> ReelMetadata:
    return ReelMetadata(
        source_url="instagram.com/reel/p4test1",
        platform="instagram",
        author="tester",
        posted_at=datetime(2024, 6, 1),
        title="Phase 4 reel",
        caption="Testing extraction wiring",
        video_path=video_path,
    )


# --- AC1: Successful extraction — status sequence includes "extracting…" then extracted summary ---

async def test_successful_extraction_status_sequence() -> None:
    conn = _make_conn()
    bot = _make_bot()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path)
    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    assert any("extracting" in c for c in calls), f"Expected 'extracting…' in calls: {calls}"
    last_call = calls[-1]
    assert "extracted" in last_call, f"Expected 'extracted' in last call: {last_call}"
    assert EXTRACTION.summary[:20] in last_call, f"Expected summary snippet in last call: {last_call}"


# --- AC2: Extraction failure — status updated with "extraction failed" and the error message ---

async def test_extraction_failure_status_update() -> None:
    conn = _make_conn()
    bot = _make_bot()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path)
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p4fail1")

    # Use a unique URL for this test
    fetch_result_fail = ReelMetadata(
        source_url="instagram.com/reel/p4fail1",
        platform="instagram",
        author="tester",
        posted_at=None,
        title="Fail reel",
        caption=None,
        video_path=video_path,
    )

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result_fail)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=Exception("quota exceeded"))):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    failure_calls = [c for c in calls if "extraction failed" in c and "quota exceeded" in c]
    assert failure_calls, f"Expected failure message, got: {calls}"


# --- AC3: Temp file cleanup on success — file deleted after successful extraction ---

async def test_temp_file_deleted_on_success() -> None:
    conn = _make_conn()
    bot = _make_bot()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    assert video_path.exists()
    fetch_result = _make_fetch_result(video_path)
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p4cleanup1")

    fetch_result_cleanup = ReelMetadata(
        source_url="instagram.com/reel/p4cleanup1",
        platform="instagram",
        author="tester",
        posted_at=None,
        title="Cleanup reel",
        caption=None,
        video_path=video_path,
    )

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result_cleanup)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    assert not video_path.exists(), f"Expected temp file to be deleted, but it still exists: {video_path}"


# --- AC4: Temp file cleanup on failure — file deleted even when extraction raises ---

async def test_temp_file_deleted_on_extraction_failure() -> None:
    conn = _make_conn()
    bot = _make_bot()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    assert video_path.exists()

    fetch_result_fail = ReelMetadata(
        source_url="instagram.com/reel/p4cleanup2",
        platform="instagram",
        author="tester",
        posted_at=None,
        title="Cleanup fail reel",
        caption=None,
        video_path=video_path,
    )

    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p4cleanup2")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result_fail)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=Exception("quota exceeded"))):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    assert not video_path.exists(), f"Expected temp file to be deleted on failure, but it still exists: {video_path}"


# --- AC5: update_extraction called — DB row has populated summary after successful extraction ---

async def test_update_extraction_persists_to_db() -> None:
    conn = _make_conn()
    bot = _make_bot()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result_db = ReelMetadata(
        source_url="instagram.com/reel/p4db1",
        platform="instagram",
        author="tester",
        posted_at=None,
        title="DB check reel",
        caption=None,
        video_path=video_path,
    )

    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p4db1")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result_db)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    stored_url = "instagram.com/reel/p4db1"
    row = await find_by_url(conn, stored_url)
    assert row is not None, "Expected reel row in DB"
    assert row["summary"] == EXTRACTION.summary, (
        f"Expected summary '{EXTRACTION.summary}', got '{row['summary']}'"
    )
    assert row["transcription"] == EXTRACTION.transcription
    assert row["ocr_text"] == EXTRACTION.ocr_text

"""Phase 3 integration tests: downloader wired into orchestrator."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import handle_message
from bot.status import StatusMessage
from pipeline.exceptions import DurationCapExceeded
from pipeline.models import ExtractionResult, Item, ReelMetadata
from storage.db import get_connection, init_db
from storage.repository import save_reel

_STUB_EXTRACTION = ExtractionResult(
    transcription="stub",
    ocr_text="stub ocr",
    summary="stub summary",
    title="stub",
    items=[],
)


def _make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    conn = get_connection(db_path)
    init_db(db_path)
    return conn


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
# Normalized form (with scheme) — what orchestrator stores/looks up after prepending https://
REEL_URL = "https://instagram.com/reel/abc123"

METADATA = ReelMetadata(
    source_url=REEL_URL,
    platform="instagram",
    author="tester",
    posted_at=datetime(2024, 1, 1),
    title="Test reel",
    caption="A test caption",
    video_path=Path("/tmp/test.mp4"),
)

EXTRACTION = ExtractionResult(
    transcription="test transcription",
    ocr_text="test ocr",
    summary="test summary",
    title="Phase Three Test Reel",
    items=[],
)


# --- AC1: fresh URL, successful download ---

async def test_fresh_url_successful_download() -> None:
    conn = _make_conn()
    bot = _make_bot()
    fetch_result = ReelMetadata(
        source_url="instagram.com/reel/fresh1",
        platform="instagram",
        author="FoodGuy",
        posted_at=None,
        title="Ramen Tour",
        caption=None,
        video_path=Path("/tmp/abc.mp4"),
    )

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/fresh1/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", MagicMock()), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=_STUB_EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    assert any("downloading" in c for c in calls)
    assert any("extracting" in c for c in calls)


# --- AC2: DurationCapExceeded raises → status updated with duration and cap ---

async def test_duration_cap_exceeded() -> None:
    conn = _make_conn()
    bot = _make_bot()

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/toolong/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", MagicMock()), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(side_effect=DurationCapExceeded(duration=180, cap=120))):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    rejection_calls = [c for c in calls if "180" in c and "120" in c]
    assert rejection_calls, f"Expected rejection message with durations, got: {calls}"


# --- AC3: generic download failure → status updated with "download failed" and error message ---

async def test_generic_download_failure() -> None:
    conn = _make_conn()
    bot = _make_bot()

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/blocked/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", MagicMock()), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(side_effect=Exception("blocked"))):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    failure_calls = [c for c in calls if "download failed" in c and "blocked" in c]
    assert failure_calls, f"Expected failure message, got: {calls}"


# --- AC4: duplicate URL → "already captured" ---

async def test_duplicate_url_already_captured() -> None:
    conn = _make_conn()
    bot = _make_bot()
    await save_reel(conn, METADATA, EXTRACTION)

    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", MagicMock()):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    assert any("already captured" in c for c in calls)


# --- AC5: status ordering — send before "downloading…" before final update ---

async def test_status_ordering_send_before_downloading_before_final() -> None:
    conn = _make_conn()
    bot = _make_bot()
    call_order: list[str] = []

    original_send = StatusMessage.send

    async def tracked_send(self: StatusMessage, chat_id: int, initial_text: str) -> None:
        call_order.append("send")
        await original_send(self, chat_id, initial_text)

    fetch_result = ReelMetadata(
        source_url="instagram.com/reel/order1",
        platform="instagram",
        author="Chef",
        posted_at=None,
        title="Sushi Night",
        caption=None,
        video_path=Path("/tmp/order1.mp4"),
    )

    update_calls: list[str] = []
    original_update = StatusMessage.update

    async def tracked_update(self: StatusMessage, text: str) -> None:
        call_order.append(f"update:{text}")
        update_calls.append(text)
        await original_update(self, text)

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/order1/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", MagicMock()), \
         patch.object(StatusMessage, "send", tracked_send), \
         patch.object(StatusMessage, "update", tracked_update), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=_STUB_EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    assert call_order[0] == "send", f"First call should be 'send', got: {call_order}"
    downloading_idx = next((i for i, e in enumerate(call_order) if "downloading" in e), None)
    assert downloading_idx is not None, f"'downloading…' update not found in: {call_order}"
    assert downloading_idx > 0, f"'downloading…' should come after 'send', got: {call_order}"
    extracting_idx = next((i for i, e in enumerate(call_order) if "extracting" in e), None)
    assert extracting_idx is not None, f"'extracting…' update not found in: {call_order}"
    assert extracting_idx > downloading_idx, f"'extracting…' should come after 'downloading…', got: {call_order}"

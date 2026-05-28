"""Phase 2 integration tests: dedup and orchestrator wiring."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import handle_message
from bot.status import StatusMessage
from pipeline.models import ExtractionResult, Item, ReelMetadata
from storage.db import get_connection, init_db
from storage.repository import save_reel
from storage import repository


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
# detect_reel extracts the matched regex portion only — no scheme, no www., no trailing slash
REEL_URL = "instagram.com/reel/abc123"

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
    items=[],
)


# --- AC1: pre-seeded URL → status updated with "already captured" ---

async def test_duplicate_url_status_contains_already_captured() -> None:
    conn = _make_conn()
    bot = _make_bot()
    await save_reel(conn, METADATA, EXTRACTION)

    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    bot.edit_message_text.assert_called_once()
    updated_text: str = bot.edit_message_text.call_args[0][0]
    assert "already captured" in updated_text


# --- AC2: fresh URL → status updated with "not yet implemented" ---

async def test_fresh_url_status_contains_not_yet_implemented() -> None:
    conn = _make_conn()
    bot = _make_bot()

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/brand_new/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    bot.edit_message_text.assert_called_once()
    updated_text: str = bot.edit_message_text.call_args[0][0]
    assert "not yet implemented" in updated_text


# --- AC3: StatusMessage.send is called before orchestrator.run ---

async def test_status_send_called_before_orchestrator_run() -> None:
    conn = _make_conn()
    bot = _make_bot()
    call_order: list[str] = []

    original_send = StatusMessage.send

    async def tracked_send(self: StatusMessage, chat_id: int, initial_text: str) -> None:
        call_order.append("send")
        await original_send(self, chat_id, initial_text)

    async def tracked_run(*args, **kwargs) -> None:
        call_order.append("run")

    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/order_test/")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch.object(StatusMessage, "send", tracked_send), \
         patch("bot.handlers.orchestrator.run", tracked_run):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    assert call_order == ["send", "run"], f"Expected ['send', 'run'], got {call_order}"


# --- AC4: duplicate path shows vault_note_path when set ---

async def test_duplicate_with_vault_path_shows_path() -> None:
    conn = _make_conn()
    bot = _make_bot()
    reel_id = await save_reel(conn, METADATA, EXTRACTION)
    vault_path = "10 Projects/Kyoto/reel.md"
    await repository.update_vault_path(conn, reel_id, vault_path)

    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    updated_text: str = bot.edit_message_text.call_args[0][0]
    assert vault_path in updated_text


# --- AC4 (integration): duplicate with no vault path shows fallback ---

async def test_duplicate_without_vault_path_shows_fallback() -> None:
    conn = _make_conn()
    bot = _make_bot()
    await save_reel(conn, METADATA, EXTRACTION)

    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        await handle_message(msg)

    updated_text: str = bot.edit_message_text.call_args[0][0]
    assert "already captured" in updated_text
    assert "note not yet written" in updated_text

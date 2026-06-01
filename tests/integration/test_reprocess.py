"""Integration tests for the /reprocess command handler."""

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import handle_reprocess
from storage.db import get_connection, init_db


def _make_message(user_id: int, text: str) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.text = text
    message.chat = MagicMock()
    message.chat.id = 100
    message.answer = AsyncMock()
    return message


def _make_bot() -> MagicMock:
    bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 1
    bot.send_message = AsyncMock(return_value=sent_msg)
    bot.edit_message_text = AsyncMock()
    return bot


def _make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    conn = get_connection(db_path)
    init_db(db_path)
    return conn


ALLOWED_ID = 12345


@pytest.fixture(autouse=True)
def patch_config_and_deps():
    mock_bot = _make_bot()
    mock_conn = _make_conn()
    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", mock_bot), \
         patch("bot.handlers._conn", mock_conn), \
         patch("bot.handlers._vault_writer", MagicMock()), \
         patch("bot.handlers.orchestrator.run", new=AsyncMock()):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        yield mock_cfg, mock_bot


# --- Test: force=True is passed to orchestrator ---

async def test_reprocess_command_calls_orchestrator_with_force_true(
    patch_config_and_deps,
) -> None:
    msg = _make_message(ALLOWED_ID, "/reprocess https://example.com/reel/abc")
    with patch("bot.handlers.orchestrator.run", new_callable=AsyncMock) as mock_run:
        await handle_reprocess(msg)
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("force") is True


# --- Test: type_hint is forwarded ---

async def test_reprocess_command_passes_type_hint(patch_config_and_deps) -> None:
    msg = _make_message(
        ALLOWED_ID, "/reprocess https://example.com/reel/abc --as tutorial"
    )
    with patch("bot.handlers.orchestrator.run", new_callable=AsyncMock) as mock_run:
        await handle_reprocess(msg)
    mock_run.assert_called_once()
    _, kwargs = mock_run.call_args
    assert kwargs.get("type_hint") == "tutorial"


# --- Test: missing URL → usage reply, no orchestrator call ---

async def test_reprocess_no_url_replies_with_usage(patch_config_and_deps) -> None:
    msg = _make_message(ALLOWED_ID, "/reprocess")
    with patch("bot.handlers.orchestrator.run", new_callable=AsyncMock) as mock_run:
        await handle_reprocess(msg)
    mock_run.assert_not_called()
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "usage" in reply_text.lower()


# --- Test: invalid type → error reply, no orchestrator call ---

async def test_reprocess_invalid_type_replies_with_error(patch_config_and_deps) -> None:
    msg = _make_message(
        ALLOWED_ID, "/reprocess https://example.com/reel/abc --as badtype"
    )
    with patch("bot.handlers.orchestrator.run", new_callable=AsyncMock) as mock_run:
        await handle_reprocess(msg)
    mock_run.assert_not_called()
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "invalid" in reply_text.lower()


# --- Test: wrong user → silently ignored ---

async def test_reprocess_ignored_for_wrong_user(patch_config_and_deps) -> None:
    msg = _make_message(99999, "/reprocess https://example.com/reel/abc")
    with patch("bot.handlers.orchestrator.run", new_callable=AsyncMock) as mock_run:
        await handle_reprocess(msg)
    mock_run.assert_not_called()
    msg.answer.assert_not_called()

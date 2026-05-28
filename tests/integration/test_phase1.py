"""Phase 1 integration tests: bot entry point and handler skeleton."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import detect_reel, handle_message
from bot.status import StatusMessage


def _make_message(user_id: int, text: str) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.text = text
    message.answer = AsyncMock()
    return message


ALLOWED_ID = 12345


@pytest.fixture(autouse=True)
def patch_config():
    with patch("bot.handlers.config") as mock_cfg:
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        yield mock_cfg


# --- AC1: wrong user ID → no reply ---

@pytest.mark.asyncio
async def test_wrong_user_no_reply() -> None:
    msg = _make_message(user_id=99999, text="https://www.instagram.com/reel/abc123/")
    await handle_message(msg)
    msg.answer.assert_not_called()


# --- AC2: URL pattern matching ---

@pytest.mark.parametrize("url,expected_platform", [
    ("https://www.instagram.com/reel/abc123/", "instagram"),
    ("https://www.instagram.com/p/abc123/", "instagram"),
    ("https://www.instagram.com/tv/abc123/", "instagram"),
    ("https://www.tiktok.com/@user/video/1234567890", "tiktok"),
    ("https://vm.tiktok.com/ZMshortcode/", "tiktok"),
    ("https://www.youtube.com/shorts/abc123", "youtube"),
    ("https://www.youtube.com/watch?v=abc123", "youtube"),
    ("https://youtu.be/abc123", "youtube"),
])
def test_detect_reel_patterns(url: str, expected_platform: str) -> None:
    result = detect_reel(url)
    assert result is not None
    _matched_url, platform = result
    assert platform == expected_platform


# --- AC3: platform routing in reply ---

@pytest.mark.asyncio
async def test_instagram_reply_contains_instagram() -> None:
    msg = _make_message(ALLOWED_ID, "check this https://www.instagram.com/reel/abc123/")
    await handle_message(msg)
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "instagram" in reply_text


@pytest.mark.asyncio
async def test_tiktok_reply_contains_tiktok() -> None:
    msg = _make_message(ALLOWED_ID, "https://www.tiktok.com/@user/video/9876543210")
    await handle_message(msg)
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "tiktok" in reply_text


@pytest.mark.asyncio
async def test_youtube_reply_contains_youtube() -> None:
    msg = _make_message(ALLOWED_ID, "https://youtu.be/dQw4w9WgXcQ")
    await handle_message(msg)
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "youtube" in reply_text


# --- AC4: StatusMessage.send stores message_id; update calls edit_message_text ---

@pytest.mark.asyncio
async def test_status_message_send_stores_message_id() -> None:
    bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 42
    bot.send_message = AsyncMock(return_value=sent_msg)
    bot.edit_message_text = AsyncMock()

    status = StatusMessage(bot)
    await status.send(chat_id=100, initial_text="starting...")

    bot.send_message.assert_called_once_with(100, "starting...")
    assert status._message_id == 42
    assert status._chat_id == 100


@pytest.mark.asyncio
async def test_status_message_update_calls_edit() -> None:
    bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 7
    bot.send_message = AsyncMock(return_value=sent_msg)
    bot.edit_message_text = AsyncMock()

    status = StatusMessage(bot)
    await status.send(chat_id=200, initial_text="initial")
    await status.update("updated text")

    bot.edit_message_text.assert_called_once_with(
        "updated text",
        chat_id=200,
        message_id=7,
    )


# --- AC5: no reel URL → no reply ---

@pytest.mark.asyncio
async def test_no_reel_url_no_reply() -> None:
    msg = _make_message(ALLOWED_ID, "hello, just a normal message")
    await handle_message(msg)
    msg.answer.assert_not_called()


@pytest.mark.asyncio
async def test_plain_url_no_reel_no_reply() -> None:
    msg = _make_message(ALLOWED_ID, "https://www.google.com/search?q=cats")
    await handle_message(msg)
    msg.answer.assert_not_called()


# --- Logger assertion tests ---

@pytest.mark.asyncio
async def test_matched_url_logs_info_reel_detected() -> None:
    import unittest
    msg = _make_message(ALLOWED_ID, "https://www.instagram.com/reel/abc123/")
    with unittest.TestCase().assertLogs("bot.handlers", level="DEBUG") as cm:
        await handle_message(msg)
    assert any("reel detected" in line and "instagram" in line for line in cm.output)


@pytest.mark.asyncio
async def test_no_url_logs_debug_no_reel_detected() -> None:
    import unittest
    msg = _make_message(ALLOWED_ID, "just a normal message")
    with unittest.TestCase().assertLogs("bot.handlers", level="DEBUG") as cm:
        await handle_message(msg)
    assert any("no reel URL detected" in line for line in cm.output)


@pytest.mark.asyncio
async def test_wrong_user_logs_debug_ignored() -> None:
    import unittest
    msg = _make_message(user_id=99999, text="https://www.instagram.com/reel/abc123/")
    with unittest.TestCase().assertLogs("bot.handlers", level="DEBUG") as cm:
        await handle_message(msg)
    assert any("ignored" in line for line in cm.output)

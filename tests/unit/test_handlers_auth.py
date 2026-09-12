"""Unit tests for the shared require_allowed_user decorator (bot/handlers.py)."""

from unittest.mock import MagicMock, patch

import config
from bot.handlers import require_allowed_user

ALLOWED_ID = 12345
OTHER_ID = 99999


def _make_message(user_id: int | None) -> MagicMock:
    message = MagicMock()
    if user_id is None:
        message.from_user = None
    else:
        message.from_user = MagicMock()
        message.from_user.id = user_id
    return message


async def test_calls_handler_when_user_is_allowed() -> None:
    calls: list[MagicMock] = []

    @require_allowed_user
    async def handler(message: MagicMock) -> None:
        calls.append(message)

    message = _make_message(ALLOWED_ID)
    with patch.object(config, "TELEGRAM_ALLOWED_USER_ID", ALLOWED_ID):
        await handler(message)

    assert calls == [message]


async def test_skips_handler_when_user_is_not_allowed() -> None:
    calls: list[MagicMock] = []

    @require_allowed_user
    async def handler(message: MagicMock) -> None:
        calls.append(message)

    message = _make_message(OTHER_ID)
    with patch.object(config, "TELEGRAM_ALLOWED_USER_ID", ALLOWED_ID):
        await handler(message)

    assert calls == []


async def test_skips_handler_when_from_user_is_none() -> None:
    calls: list[MagicMock] = []

    @require_allowed_user
    async def handler(message: MagicMock) -> None:
        calls.append(message)

    message = _make_message(None)
    with patch.object(config, "TELEGRAM_ALLOWED_USER_ID", ALLOWED_ID):
        await handler(message)

    assert calls == []

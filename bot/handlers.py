"""Telegram message and command handlers."""

import functools
import logging
import re
import sqlite3
from typing import Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

import config
from bot.status import StatusMessage
from output.writers import VaultWriter
from pipeline import orchestrator
from reelkit.urls import detect_reel

logger = logging.getLogger(__name__)


def require_allowed_user(
    handler: Callable[[Message], Awaitable[None]],
) -> Callable[[Message], Awaitable[None]]:
    """Silently drops any message not from the configured owner."""

    @functools.wraps(handler)
    async def wrapper(message: Message) -> None:
        if message.from_user is None or message.from_user.id != config.TELEGRAM_ALLOWED_USER_ID:
            logger.debug(
                "ignored: wrong user %s",
                message.from_user.id if message.from_user else None,
            )
            return
        await handler(message)

    return wrapper


_bot: Bot | None = None
_conn: sqlite3.Connection | None = None
_vault_writer: VaultWriter | None = None


_VALID_TYPES: frozenset[str] = frozenset({"list", "tutorial", "other"})
_URL_RE: re.Pattern[str] = re.compile(r"https?://\S+")


def _parse_reprocess_args(text: str) -> tuple[str | None, str | None, str | None]:
    """Parse '/reprocess' command text.

    Returns (url, type_hint, error_message).
    - On success: (url, type_hint_or_None, None)
    - On validation failure: (None, None, error_message)
    """
    # Strip the leading command token (/reprocess[@botname])
    parts = text.split(maxsplit=1)
    remainder = parts[1].strip() if len(parts) > 1 else ""

    if not remainder:
        return None, None, "usage: /reprocess <URL> [--as list|tutorial|other]"

    # Extract --as <type> if present
    type_hint: str | None = None
    as_match = re.search(r"--as\s+(\S+)", remainder)
    if as_match:
        raw_type = as_match.group(1)
        if raw_type not in _VALID_TYPES:
            return None, None, "invalid type · must be list, tutorial, or other"
        type_hint = raw_type
        # Remove the --as token so we can find the URL cleanly
        remainder = remainder[: as_match.start()] + remainder[as_match.end() :]

    # Find URL in whatever remains
    url_match = _URL_RE.search(remainder)
    if url_match is None:
        return None, None, "usage: /reprocess <URL> [--as list|tutorial|other]"

    url = url_match.group(0)
    return url, type_hint, None


@require_allowed_user
async def handle_reprocess(message: Message) -> None:
    assert _bot is not None and _conn is not None and _vault_writer is not None
    logger.debug(
        "reprocess command from user %s",
        message.from_user.id if message.from_user else None,
    )

    raw_text = message.text or ""
    url, type_hint, error = _parse_reprocess_args(raw_text)
    if error is not None:
        await message.answer(error)
        return

    assert url is not None
    logger.info("reprocess requested — url=%s type_hint=%s", url, type_hint)

    status = StatusMessage(_bot)
    await status.send(message.chat.id, "reprocessing…")
    await orchestrator.run(url, status, _conn, _vault_writer, force_reprocess=True, type_hint=type_hint)


@require_allowed_user
async def handle_message(message: Message) -> None:
    assert _bot is not None and _conn is not None and _vault_writer is not None
    logger.debug("message received from user %s", message.from_user.id if message.from_user else None)

    if not message.text:
        return

    result = detect_reel(message.text)
    if result is None:
        logger.debug("no reel URL detected")
        return

    url, platform = result
    logger.info("reel detected — %s %s", platform, url)

    status = StatusMessage(_bot)
    await status.send(message.chat.id, f"detected {platform} reel — processing...")
    await orchestrator.run(url, status, _conn, _vault_writer)


@require_allowed_user
async def handle_force(message: Message) -> None:
    assert _bot is not None and _conn is not None and _vault_writer is not None
    logger.debug("force command from user %s", message.from_user.id if message.from_user else None)

    if not message.text:
        return

    result = detect_reel(message.text)
    if result is None:
        await message.answer("usage: /force <URL>")
        return

    url, platform = result
    logger.info("force detected — %s %s", platform, url)

    status = StatusMessage(_bot)
    await status.send(message.chat.id, f"detected {platform} reel — processing...")
    await orchestrator.run(url, status, _conn, _vault_writer, skip_length_check=True)


def register_handlers(
    dp: Dispatcher, bot: Bot, conn: sqlite3.Connection, vault_writer: VaultWriter
) -> None:
    global _bot, _conn, _vault_writer
    _bot = bot
    _conn = conn
    _vault_writer = vault_writer
    dp.message.register(handle_reprocess, Command("reprocess"))
    dp.message.register(handle_force, Command("force"))
    dp.message.register(handle_message)

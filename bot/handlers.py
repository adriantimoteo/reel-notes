"""Telegram message and command handlers."""

import logging
import re
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.types import Message

import config
from bot.status import StatusMessage
from output.writers import VaultWriter
from pipeline import orchestrator

logger = logging.getLogger(__name__)

_REEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"instagram\.com/(?:reel|p|tv)/[\w-]+"), "instagram"),
    (re.compile(r"tiktok\.com/@[\w.]+/video/\d+"), "tiktok"),
    (re.compile(r"vm\.tiktok\.com/[\w]+"), "tiktok"),
    (re.compile(r"youtube\.com/shorts/[\w-]+"), "youtube"),
    (re.compile(r"youtube\.com/watch\?(?:[\w=&]*&)?v=[\w-]+"), "youtube"),
    (re.compile(r"youtu\.be/[\w-]+"), "youtube"),
]

_bot: Bot | None = None
_conn: sqlite3.Connection | None = None
_vault_writer: VaultWriter | None = None


def detect_reel(text: str) -> tuple[str, str] | None:
    for pattern, platform in _REEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0), platform
    return None


async def handle_message(message: Message) -> None:
    assert _bot is not None and _conn is not None and _vault_writer is not None
    logger.debug("message received from user %s", message.from_user.id if message.from_user else None)
    if message.from_user is None or message.from_user.id != config.TELEGRAM_ALLOWED_USER_ID:
        logger.debug("ignored: wrong user %s", message.from_user.id if message.from_user else None)
        return

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


def register_handlers(
    dp: Dispatcher, bot: Bot, conn: sqlite3.Connection, vault_writer: VaultWriter
) -> None:
    global _bot, _conn, _vault_writer
    _bot = bot
    _conn = conn
    _vault_writer = vault_writer
    dp.message.register(handle_message)

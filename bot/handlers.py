"""Telegram message and command handlers."""

import re

from aiogram import Dispatcher
from aiogram.types import Message

import config

_REEL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"instagram\.com/(?:reel|p|tv)/[\w-]+"), "instagram"),
    (re.compile(r"tiktok\.com/@[\w.]+/video/\d+"), "tiktok"),
    (re.compile(r"vm\.tiktok\.com/[\w]+"), "tiktok"),
    (re.compile(r"youtube\.com/shorts/[\w-]+"), "youtube"),
    (re.compile(r"youtube\.com/watch\?(?:[\w=&]*&)?v=[\w-]+"), "youtube"),
    (re.compile(r"youtu\.be/[\w-]+"), "youtube"),
]


def detect_reel(text: str) -> tuple[str, str] | None:
    for pattern, platform in _REEL_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0), platform
    return None


async def handle_message(message: Message) -> None:
    if message.from_user is None or message.from_user.id != config.TELEGRAM_ALLOWED_USER_ID:
        return

    if not message.text:
        return

    result = detect_reel(message.text)
    if result is None:
        return

    _url, platform = result
    await message.answer(f"detected {platform} reel — processing...")


def register_handlers(dp: Dispatcher) -> None:
    dp.message.register(handle_message)

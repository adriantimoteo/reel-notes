"""Drain-and-exit mode: process whatever updates are already queued, then stop."""

import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetUpdates

logger = logging.getLogger(__name__)


async def drain_pending(bot: Bot, dp: Dispatcher, poll_timeout: int = 0) -> int | None:
    """Process every update Telegram is currently holding for this bot, then return.

    Returns the number of updates processed, or None if the bot appears to be
    offline (network error on the first call) — treated as "try again later",
    not a failure.
    """
    offset: int | None = None
    processed = 0

    while True:
        get_updates = GetUpdates(offset=offset, timeout=poll_timeout, allowed_updates=["message"])
        try:
            updates = await bot(get_updates)
        except TelegramNetworkError as e:
            logger.warning("offline — skipping this run (%s)", e)
            return None

        if not updates:
            return processed

        for update in updates:
            await dp.feed_update(bot, update)
            offset = update.update_id + 1
            processed += 1

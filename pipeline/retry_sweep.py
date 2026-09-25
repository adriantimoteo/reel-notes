"""Retries reels whose earlier run failed after download (e.g. a Gemini 503).

Such a reel leaves a DB row with no note path. Each scheduled run retries those
rows, up to MAX_RETRY_ATTEMPTS times, and messages the owner only when a retry
succeeds or the reel is given up on — with the link, so it can be resent later.
"""

import logging
import sqlite3
import time

from aiogram import Bot

import config
from output.writers import VaultWriter
from pipeline import orchestrator
from storage import repository

logger = logging.getLogger(__name__)

MAX_RETRY_ATTEMPTS = 3
# The task runs hourly and won't start a run while another is going, so a long
# backlog must not eat the next slot. Reels not reached in time are left
# untouched (no attempt used) and go first on the next run.
RETRY_TIME_BUDGET_SECONDS = 40 * 60


class _CollectingStatus:
    """A StatusReporter that keeps the last update instead of sending it anywhere."""

    def __init__(self) -> None:
        self.last = ""

    async def update(self, text: str) -> None:
        self.last = text


async def find_pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return await repository.find_retryable(conn, MAX_RETRY_ATTEMPTS)


async def _notify(bot: Bot, text: str) -> None:
    try:
        await bot.send_message(config.TELEGRAM_ALLOWED_USER_ID, text)
    except Exception as e:
        logger.warning("could not send retry notification: %s", e)


async def retry_pending(
    bot: Bot,
    conn: sqlite3.Connection,
    vault_writer: VaultWriter,
    pending: list[sqlite3.Row],
    time_budget: float = RETRY_TIME_BUDGET_SECONDS,
) -> None:
    """Re-runs each of `pending`, which the caller collected earlier with find_pending().

    Stops starting new retries once `time_budget` seconds have passed.
    """
    started = time.monotonic()
    for index, row in enumerate(pending):
        if time.monotonic() - started >= time_budget:
            logger.info(
                "retry time budget (%ds) used up — leaving %d reel(s) for the next run",
                time_budget, len(pending) - index,
            )
            break

        url = row["source_url"]
        latest = await repository.find_by_url(conn, url)
        if latest is None or latest["id"] != row["id"] or latest["vault_note_path"]:
            logger.info("skipping retry for %s — already handled earlier in this run", url)
            continue

        attempts = row["attempts"] + 1
        await repository.bump_attempts(conn, row["id"])
        logger.info("retrying %s (attempt %d/%d)", url, attempts, MAX_RETRY_ATTEMPTS)

        status = _CollectingStatus()
        ok = await orchestrator.run(url, status, conn, vault_writer, prior_attempts=attempts)
        if ok:
            await _notify(bot, f"retry succeeded · {status.last}")
            continue

        current = await repository.find_by_url(conn, url)
        gave_up = (
            current is None
            or current["attempts"] >= MAX_RETRY_ATTEMPTS
            or current["retryable"] == 0
        )
        if gave_up:
            await _notify(
                bot,
                f"{status.last}\nnot retrying automatically — resend the link to try again",
            )
        else:
            logger.info("retry failed for %s, will try again next run: %s", url, status.last)

"""Pipeline orchestration logic."""

import logging
import sqlite3

from bot.status import StatusMessage
from storage import repository

logger = logging.getLogger(__name__)


async def run(url: str, status: StatusMessage, conn: sqlite3.Connection) -> None:
    existing = await repository.find_by_url(conn, url)
    if existing:
        note_path = existing["vault_note_path"] or "(note not yet written)"
        await status.update(f"already captured · {note_path}")
        return

    await status.update("processing not yet implemented")

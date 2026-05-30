"""Pipeline orchestration logic."""

import logging
import sqlite3

from bot.status import StatusMessage
from pipeline import downloader
from pipeline.exceptions import DurationCapExceeded
from storage import repository

logger = logging.getLogger(__name__)


async def run(url: str, status: StatusMessage, conn: sqlite3.Connection) -> None:
    if "://" not in url:
        url = "https://" + url
    existing = await repository.find_by_url(conn, url)
    if existing:
        logger.info("duplicate detected — %s", url)
        note_path = existing["vault_note_path"] or "(note not yet written)"
        await status.update(f"already captured · {note_path}")
        return

    await status.update("downloading…")
    try:
        metadata = await downloader.fetch(url)
    except DurationCapExceeded as e:
        await status.update(f"rejected · video is {e.duration}s, limit is {e.cap}s")
        return
    except Exception as e:
        await status.update(f"download failed · {e}")
        return

    logger.info("download complete for %s", url)
    await status.update(f"downloaded · {metadata.title or url} by {metadata.author or 'unknown'} · {metadata.video_path.name}")

"""Pipeline orchestration logic."""

import logging
import sqlite3

from bot.status import StatusMessage
from pipeline import downloader, extractor
from pipeline.exceptions import DurationCapExceeded
from pipeline.models import ExtractionResult
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
        logger.error("download failed for %s: %s", url, e)
        await status.update(f"download failed · {e}")
        return

    reel_id = await repository.save_reel(conn, metadata, ExtractionResult(transcription="", ocr_text="", summary=""))
    logger.info("download complete for %s", url)
    await status.update("extracting…")

    try:
        extraction = await extractor.extract(metadata)
    except Exception as e:
        logger.error("extraction failed for %s: %s", url, e)
        await status.update(f"extraction failed · {e}")
        return
    finally:
        try:
            metadata.video_path.unlink(missing_ok=True)
        except Exception:
            pass

    await repository.update_extraction(conn, reel_id, extraction)
    logger.info("extraction complete for %s", url)

    item_names = ", ".join(i.name for i in extraction.items[:3])
    await status.update(f"extracted · {extraction.summary[:100]}… | items: {item_names or 'none'}")

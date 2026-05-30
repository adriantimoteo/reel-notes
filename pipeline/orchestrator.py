"""Pipeline orchestration logic."""

import asyncio
import logging
import sqlite3

import config
from bot.status import StatusMessage
from output import renderer
from output.writers import VaultWriter
from pipeline import downloader, extractor
from pipeline.exceptions import DurationCapExceeded
from pipeline.models import ExtractionResult
from storage import repository

logger = logging.getLogger(__name__)


async def run(
    url: str,
    status: StatusMessage,
    conn: sqlite3.Connection,
    vault_writer: VaultWriter,
) -> None:
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

    try:
        filename = renderer.generate_filename(metadata)
        content = renderer.render(metadata, extraction)
        note_path = await asyncio.to_thread(vault_writer.write, filename, content)
        await repository.update_vault_path(conn, reel_id, str(note_path.relative_to(config.VAULT_PATH)))
    except Exception as e:
        logger.error("save failed for %s: %s", url, e)
        await status.update(f"save failed · {e}")
        return

    logger.info("note saved: %s", note_path.name)
    await status.update(f"saved · {note_path.name}")

"""Pipeline orchestration logic."""

import asyncio
import logging
import sqlite3

import config
from bot.status import StatusMessage
from output import renderer
from output.writers import VaultWriter
from pipeline import downloader, extractor
from pipeline.exceptions import (
    DownloadError,
    DurationCapExceeded,
    ExtractionError,
    ReelCaptureError,
    StorageError,
    UnsupportedPlatformError,
    VaultWriteError,
)
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

    try:
        await status.update("downloading…")
        try:
            metadata = await downloader.fetch(url)
        except (DurationCapExceeded, UnsupportedPlatformError):
            raise
        except Exception as e:
            logger.error("download failed for %s: %s", url, e)
            raise DownloadError(url=url, cause=e) from e

        reel_id = await repository.save_reel(
            conn, metadata, ExtractionResult(transcription="", ocr_text="", summary="", title="")
        )
        logger.info("download complete for %s", url)
        await status.update("extracting…")

        try:
            extraction = await extractor.extract(metadata)
        except ReelCaptureError:
            raise
        except Exception as e:
            logger.error("extraction failed for %s: %s", url, e)
            raise ExtractionError(cause=e) from e
        finally:
            try:
                metadata.video_path.unlink(missing_ok=True)
            except Exception as cleanup_exc:
                logger.warning("failed to delete temp file %s: %s", metadata.video_path, cleanup_exc)

        await repository.update_extraction(conn, reel_id, extraction)
        logger.info("extraction complete for %s", url)

        filename = renderer.generate_filename(metadata, extraction)
        content = renderer.render(metadata, extraction)
        try:
            note_path = await asyncio.to_thread(vault_writer.write, filename, content)
        except Exception as e:
            logger.error("vault write failed for %s: %s", url, e)
            raise VaultWriteError(path=filename, cause=e) from e

        try:
            await repository.update_vault_path(
                conn, reel_id, str(note_path.relative_to(config.VAULT_PATH))
            )
        except Exception as e:
            logger.error("storage failed for %s: %s", url, e)
            raise StorageError(cause=e) from e

        logger.info("note saved: %s", note_path.name)
        await status.update(f"saved · {note_path.name}")

    except ReelCaptureError as exc:
        if isinstance(exc, UnsupportedPlatformError):
            msg = "unsupported URL"
        elif isinstance(exc, DurationCapExceeded):
            msg = f"rejected · video is {exc.duration}s (limit {exc.cap}s)"
        elif isinstance(exc, DownloadError):
            msg = f"download failed · {exc.cause}"
        elif isinstance(exc, ExtractionError):
            msg = f"extraction failed · {exc.cause}"
        elif isinstance(exc, StorageError):
            msg = f"save failed · {exc.cause}"
        elif isinstance(exc, VaultWriteError):
            msg = f"vault write failed · {exc.path} · {exc.cause}"
        else:
            msg = f"pipeline error · {exc}"
        await status.update(msg)
    except Exception as exc:
        logger.error("unexpected error for %s: %s", url, exc)
        await status.update(f"pipeline error · {exc}")

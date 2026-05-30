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

ERROR_MESSAGES = {
    UnsupportedPlatformError: lambda e: "unsupported URL",
    DurationCapExceeded:      lambda e: f"rejected · video is {e.duration}s (limit {e.cap}s)",
    DownloadError:            lambda e: f"download failed · {e.cause}",
    ExtractionError:          lambda e: f"extraction failed · {e.cause}",
    StorageError:             lambda e: f"save failed · {e.cause}",
    VaultWriteError:          lambda e: f"vault write failed · {e.path} · {e.cause}",
    ReelCaptureError:         lambda e: f"pipeline error · {e}",
}


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
            except Exception:
                pass

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
        for exc_type, msg_fn in ERROR_MESSAGES.items():
            if isinstance(exc, exc_type):
                await status.update(msg_fn(exc))
                return
    except Exception as exc:
        logger.error("unexpected error for %s: %s", url, exc)
        await status.update(f"pipeline error · {exc}")

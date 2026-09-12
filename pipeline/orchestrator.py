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
    UnsupportedCarouselError,
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
    force_reprocess: bool = False,
    skip_length_check: bool = False,
    type_hint: str | None = None,
) -> None:
    if "://" not in url:
        url = "https://" + url

    existing_note_path: str | None = None

    if not force_reprocess:
        existing = await repository.find_by_url(conn, url)
        if existing:
            logger.info("duplicate detected — %s", url)
            note_path = existing["vault_note_path"] or "(note not yet written)"
            await status.update(f"already captured · {note_path}")
            return
    else:
        existing = await repository.find_by_url(conn, url)
        existing_note_path = existing["vault_note_path"] if existing else None

    try:
        await status.update("downloading…")
        try:
            max_duration = config.FORCE_MAX_VIDEO_DURATION_SECONDS if skip_length_check else None
            metadata = await downloader.fetch(url, max_duration=max_duration)
        except (DurationCapExceeded, UnsupportedPlatformError):
            raise
        except Exception as e:
            logger.error("download failed for %s: %s", url, e)
            raise DownloadError(url=url, cause=e) from e

        if force_reprocess:
            if existing_note_path:
                old_file = config.VAULT_PATH / existing_note_path
                try:
                    old_file.unlink(missing_ok=True)
                    logger.info("deleted old note: %s", existing_note_path)
                except Exception as e:
                    logger.warning("failed to delete old note %s: %s", existing_note_path, e)
            await repository.delete_by_url(conn, url)

        try:
            try:
                reel_id = await repository.save_reel(
                    conn, metadata, ExtractionResult(transcription="", ocr_text="", summary="", title="")
                )
            except Exception as e:
                logger.error("storage failed for %s: %s", url, e)
                raise StorageError(cause=e) from e

            logger.info("download complete for %s", url)
            await status.update("extracting…")

            try:
                extraction = await extractor.extract(metadata, type_hint=type_hint)
            except ReelCaptureError:
                raise
            except Exception as e:
                logger.error("extraction failed for %s: %s", url, e)
                raise ExtractionError(cause=e) from e
        finally:
            for temp_path in metadata.temp_paths():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception as cleanup_exc:
                    logger.warning("failed to delete temp file %s: %s", temp_path, cleanup_exc)

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
        if isinstance(exc, UnsupportedCarouselError):
            msg = "unsupported · YouTube photo/carousel posts aren't supported yet"
        elif isinstance(exc, UnsupportedPlatformError):
            msg = "unsupported URL"
        elif isinstance(exc, DurationCapExceeded):
            msg = f"rejected · video is {exc.duration}s (limit {exc.cap}s)"
        elif isinstance(exc, DownloadError):
            cause_str = str(exc.cause)
            if "empty media response" in cause_str:
                msg = "download failed · Instagram requires authentication — set YTDLP_COOKIES_FILE in .env"
            elif "Could not copy" in cause_str and "cookie database" in cause_str:
                msg = "download failed · browser cookie access blocked — use YTDLP_COOKIES_FILE instead of YTDLP_COOKIES_FROM_BROWSER"
            else:
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

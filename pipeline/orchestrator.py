"""Pipeline orchestration logic."""

import asyncio
import logging
import sqlite3

import httpx

import config
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
from reelkit import gemini
from reelkit.status import StatusReporter
from storage import repository

logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    """True for failures worth retrying on a later run: Gemini 5xx/429 and network drops."""
    if not isinstance(exc, ExtractionError):
        return False
    cause = exc.cause
    return gemini.is_retryable_error(cause) or isinstance(
        cause, (ConnectionError, TimeoutError, httpx.TransportError)
    )


async def _record_failure(conn: sqlite3.Connection, reel_id: int | None, exc: Exception) -> None:
    """Flags the reel's DB row so the next run's retry sweep knows whether to pick it up."""
    if reel_id is None:
        return
    try:
        await repository.mark_failed(conn, reel_id, str(exc), retryable=_is_transient(exc))
    except Exception as e:
        logger.warning("could not record failure for reel %s: %s", reel_id, e)


async def run(
    url: str,
    status: StatusReporter,
    conn: sqlite3.Connection,
    vault_writer: VaultWriter,
    force_reprocess: bool = False,
    skip_length_check: bool = False,
    type_hint: str | None = None,
    prior_attempts: int = 0,
) -> bool:
    """Runs the pipeline for one URL. Returns False if it failed, True otherwise
    (saved, or already captured). `prior_attempts` carries the retry count of a
    reel being retried by the sweep so it survives the row being re-created."""
    if "://" not in url:
        url = "https://" + url

    try:
        canonical_url, _ = await downloader.resolve_canonical_url(url)
    except UnsupportedPlatformError:
        canonical_url = url

    existing = await repository.find_by_url(conn, canonical_url)
    existing_note_path: str | None = existing["vault_note_path"] if existing else None

    if existing and existing_note_path and not force_reprocess:
        logger.info("duplicate detected — %s", canonical_url)
        if (config.VAULT_PATH / existing_note_path).exists():
            await status.update(f"already captured · {existing_note_path}")
        else:
            await status.update(
                f"already processed, but its note has since been deleted · {existing_note_path}"
                f"\n/reprocess {url} to regenerate it"
            )
        return True

    # A row with no note path is a leftover from an earlier failed run, not a
    # duplicate: fall through and process it again, replacing the stale row.
    reel_id: int | None = None

    try:
        await status.update("downloading…")
        try:
            max_duration = config.FORCE_MAX_VIDEO_DURATION_SECONDS if skip_length_check else None
            metadata = await downloader.fetch(canonical_url, max_duration=max_duration)
        except (DurationCapExceeded, UnsupportedPlatformError):
            raise
        except Exception as e:
            logger.error("download failed for %s: %s", url, e)
            raise DownloadError(url=url, cause=e) from e

        if force_reprocess or existing:
            if existing_note_path:
                old_file = config.VAULT_PATH / existing_note_path
                try:
                    old_file.unlink(missing_ok=True)
                    logger.info("deleted old note: %s", existing_note_path)
                except Exception as e:
                    logger.warning("failed to delete old note %s: %s", existing_note_path, e)
            await repository.delete_by_url(conn, canonical_url)

        try:
            try:
                reel_id = await repository.save_reel(
                    conn,
                    metadata,
                    ExtractionResult(transcription="", ocr_text="", summary="", title=""),
                    attempts=prior_attempts,
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
        return True

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
            cause = exc.cause
            if gemini.is_model_retired(cause):
                detail = getattr(cause, "message", None) or str(cause)
                msg = f"extraction failed · Gemini model retired — update pipeline.extractor.MODEL_NAME · {detail}"
            else:
                msg = f"extraction failed · {exc.cause}"
        elif isinstance(exc, StorageError):
            msg = f"save failed · {exc.cause}"
        elif isinstance(exc, VaultWriteError):
            msg = f"vault write failed · {exc.path} · {exc.cause}"
        else:
            msg = f"pipeline error · {exc}"
        await _record_failure(conn, reel_id, exc)
        await status.update(f"{msg}\n{url}")
        return False
    except Exception as exc:
        logger.error("unexpected error for %s: %s", url, exc)
        await _record_failure(conn, reel_id, exc)
        await status.update(f"pipeline error · {exc}\n{url}")
        return False

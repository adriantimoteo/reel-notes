"""Data access repository."""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone

from pipeline.models import ExtractionResult, ReelMetadata

logger = logging.getLogger(__name__)


def _find_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    logger.debug("find_by_url: %s", url)
    return conn.execute(
        "SELECT * FROM reels WHERE source_url = ?", (url,)
    ).fetchone()


async def find_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return await asyncio.to_thread(_find_by_url, conn, url)


def _save_reel(
    conn: sqlite3.Connection,
    metadata: ReelMetadata,
    extraction: ExtractionResult,
    attempts: int = 0,
) -> int:
    logger.debug("save_reel: %s", metadata.source_url)
    posted_at = metadata.posted_at.isoformat() if metadata.posted_at is not None else None
    cursor = conn.execute(
        """
        INSERT INTO reels (
            source_url, platform, author, posted_at, captured_at,
            title, caption, transcription, ocr_text, summary, content_type, attempts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metadata.source_url,
            metadata.platform,
            metadata.author,
            posted_at,
            datetime.now(timezone.utc).isoformat(),
            metadata.title,
            metadata.caption,
            extraction.transcription,
            extraction.ocr_text,
            extraction.summary,
            extraction.content_type,
            attempts,
        ),
    )
    reel_id = cursor.lastrowid
    conn.commit()
    return reel_id


async def save_reel(
    conn: sqlite3.Connection,
    metadata: ReelMetadata,
    extraction: ExtractionResult,
    attempts: int = 0,
) -> int:
    return await asyncio.to_thread(_save_reel, conn, metadata, extraction, attempts)


def _update_vault_path(
    conn: sqlite3.Connection, reel_id: int, vault_note_path: str
) -> None:
    logger.debug("update_vault_path: reel_id=%s", reel_id)
    conn.execute(
        "UPDATE reels SET vault_note_path = ? WHERE id = ?",
        (vault_note_path, reel_id),
    )
    conn.commit()


async def update_vault_path(
    conn: sqlite3.Connection, reel_id: int, vault_note_path: str
) -> None:
    await asyncio.to_thread(_update_vault_path, conn, reel_id, vault_note_path)


def _update_extraction(conn: sqlite3.Connection, reel_id: int, extraction: ExtractionResult) -> None:
    conn.execute(
        "UPDATE reels SET transcription=?, ocr_text=?, summary=?, content_type=? WHERE id=?",
        (extraction.transcription, extraction.ocr_text, extraction.summary, extraction.content_type, reel_id),
    )
    conn.commit()


async def update_extraction(conn: sqlite3.Connection, reel_id: int, extraction: ExtractionResult) -> None:
    await asyncio.to_thread(_update_extraction, conn, reel_id, extraction)


def _delete_by_url(conn: sqlite3.Connection, url: str) -> None:
    logger.debug("delete_by_url: %s", url)
    conn.execute("DELETE FROM reels WHERE source_url = ?", (url,))
    conn.commit()


async def delete_by_url(conn: sqlite3.Connection, url: str) -> None:
    await asyncio.to_thread(_delete_by_url, conn, url)


def _mark_failed(conn: sqlite3.Connection, reel_id: int, error: str, retryable: bool) -> None:
    logger.debug("mark_failed: reel_id=%s retryable=%s", reel_id, retryable)
    conn.execute(
        "UPDATE reels SET last_error = ?, retryable = ? WHERE id = ?",
        (error, int(retryable), reel_id),
    )
    conn.commit()


async def mark_failed(conn: sqlite3.Connection, reel_id: int, error: str, retryable: bool) -> None:
    await asyncio.to_thread(_mark_failed, conn, reel_id, error, retryable)


def _find_retryable(conn: sqlite3.Connection, max_attempts: int) -> list[sqlite3.Row]:
    # retryable IS NULL covers rows left behind before failures were classified.
    return conn.execute(
        """
        SELECT * FROM reels
        WHERE (vault_note_path IS NULL OR vault_note_path = '')
          AND attempts < ?
          AND COALESCE(retryable, 1) = 1
        ORDER BY id
        """,
        (max_attempts,),
    ).fetchall()


async def find_retryable(conn: sqlite3.Connection, max_attempts: int) -> list[sqlite3.Row]:
    """Reels whose note was never written and that are still worth retrying."""
    return await asyncio.to_thread(_find_retryable, conn, max_attempts)


def _bump_attempts(conn: sqlite3.Connection, reel_id: int) -> None:
    conn.execute("UPDATE reels SET attempts = attempts + 1 WHERE id = ?", (reel_id,))
    conn.commit()


async def bump_attempts(conn: sqlite3.Connection, reel_id: int) -> None:
    await asyncio.to_thread(_bump_attempts, conn, reel_id)

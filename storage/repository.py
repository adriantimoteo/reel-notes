"""Data access repository."""

import asyncio
import logging
import sqlite3
from datetime import datetime

from pipeline.models import ExtractionResult, Item, ReelMetadata

logger = logging.getLogger(__name__)


def _find_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    logger.debug(f"find_by_url: {url}")
    return conn.execute(
        "SELECT * FROM reels WHERE source_url = ?", (url,)
    ).fetchone()


async def find_by_url(conn: sqlite3.Connection, url: str) -> sqlite3.Row | None:
    return await asyncio.to_thread(_find_by_url, conn, url)


def _save_items(conn: sqlite3.Connection, reel_id: int, items: list[Item]) -> None:
    if not items:
        return
    conn.executemany(
        "INSERT INTO items (reel_id, name, item_type, description) VALUES (?, ?, ?, ?)",
        [(reel_id, item.name, item.item_type, item.description) for item in items],
    )


def _save_reel(
    conn: sqlite3.Connection,
    metadata: ReelMetadata,
    extraction: ExtractionResult,
) -> int:
    logger.debug(f"save_reel: {metadata.source_url}")
    posted_at = metadata.posted_at.isoformat() if metadata.posted_at is not None else None
    cursor = conn.execute(
        """
        INSERT INTO reels (
            source_url, platform, author, posted_at, captured_at,
            title, caption, transcription, ocr_text, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metadata.source_url,
            metadata.platform,
            metadata.author,
            posted_at,
            datetime.utcnow().isoformat(),
            metadata.title,
            metadata.caption,
            extraction.transcription,
            extraction.ocr_text,
            extraction.summary,
        ),
    )
    reel_id = cursor.lastrowid
    _save_items(conn, reel_id, extraction.items)
    return reel_id


async def save_reel(
    conn: sqlite3.Connection,
    metadata: ReelMetadata,
    extraction: ExtractionResult,
) -> int:
    return await asyncio.to_thread(_save_reel, conn, metadata, extraction)


def _update_vault_path(
    conn: sqlite3.Connection, reel_id: int, vault_note_path: str
) -> None:
    logger.debug(f"update_vault_path: reel_id={reel_id}")
    conn.execute(
        "UPDATE reels SET vault_note_path = ? WHERE id = ?",
        (vault_note_path, reel_id),
    )


async def update_vault_path(
    conn: sqlite3.Connection, reel_id: int, vault_note_path: str
) -> None:
    await asyncio.to_thread(_update_vault_path, conn, reel_id, vault_note_path)

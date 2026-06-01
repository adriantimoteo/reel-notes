"""Unit tests for storage/repository.py."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from pipeline.models import ExtractionResult, Item, ReelMetadata
from storage.db import get_connection, init_db
from storage.repository import delete_by_url, find_by_url, save_reel, update_extraction, update_vault_path


def make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    conn = get_connection(db_path)
    init_db(db_path)
    return conn


METADATA = ReelMetadata(
    source_url="https://www.instagram.com/reel/abc123/",
    platform="instagram",
    author="travel_guru",
    posted_at=datetime(2024, 3, 15, 10, 30, 0),
    title="Best spots in Kyoto",
    caption="Don't miss these hidden gems! #kyoto #travel",
    video_path=Path("/tmp/abc123.mp4"),
    hashtags=["kyoto", "travel"],
)

EXTRACTION = ExtractionResult(
    transcription="Welcome to Kyoto. Here are my favourite spots.",
    ocr_text="Fushimi Inari — open 24 hours",
    summary="A guide to hidden gems in Kyoto including temples and food spots.",
    title="Kyoto Hidden Gems Guide",
    items=[
        Item(name="Fushimi Inari", item_type="place", description="Famous torii gates, best at dawn."),
        Item(name="Nishiki Market", item_type="place", description="Street food and fresh produce."),
    ],
)


async def test_find_by_url_returns_none_for_unseen_url() -> None:
    conn = make_conn()
    result = await find_by_url(conn, "https://www.instagram.com/reel/notexist/")
    assert result is None


async def test_find_by_url_returns_row_after_save() -> None:
    conn = make_conn()
    await save_reel(conn, METADATA, EXTRACTION)
    result = await find_by_url(conn, METADATA.source_url)
    assert result is not None
    assert result["source_url"] == METADATA.source_url


async def test_save_reel_returns_positive_integer_reel_id() -> None:
    conn = make_conn()
    reel_id = await save_reel(conn, METADATA, EXTRACTION)
    assert isinstance(reel_id, int)
    assert reel_id > 0


async def test_save_reel_inserts_items() -> None:
    conn = make_conn()
    reel_id = await save_reel(conn, METADATA, EXTRACTION)
    rows = conn.execute(
        "SELECT * FROM items WHERE reel_id = ?", (reel_id,)
    ).fetchall()
    assert len(rows) == len(EXTRACTION.items)
    names = {row["name"] for row in rows}
    assert names == {item.name for item in EXTRACTION.items}


async def test_update_vault_path_persists() -> None:
    conn = make_conn()
    reel_id = await save_reel(conn, METADATA, EXTRACTION)
    vault_path = "10 Projects/Kyoto Reels/best-spots-kyoto.md"
    await update_vault_path(conn, reel_id, vault_path)
    row = await find_by_url(conn, METADATA.source_url)
    assert row is not None
    assert row["vault_note_path"] == vault_path


async def test_save_reel_duplicate_url_raises_integrity_error() -> None:
    conn = make_conn()
    await save_reel(conn, METADATA, EXTRACTION)
    with pytest.raises(sqlite3.IntegrityError):
        await save_reel(conn, METADATA, EXTRACTION)


async def test_update_extraction_persists_fields() -> None:
    conn = make_conn()
    empty = ExtractionResult(transcription="", ocr_text="", summary="", title="")
    reel_id = await save_reel(conn, METADATA, empty)
    updated = ExtractionResult(
        transcription="new transcription",
        ocr_text="new ocr",
        summary="new summary",
        title="Updated Title",
        items=[],
        content_type="tutorial",
    )
    await update_extraction(conn, reel_id, updated)
    row = await find_by_url(conn, METADATA.source_url)
    assert row is not None
    assert row["transcription"] == "new transcription"
    assert row["ocr_text"] == "new ocr"
    assert row["summary"] == "new summary"
    assert row["content_type"] == "tutorial"


async def test_save_reel_persists_null_content_type() -> None:
    conn = make_conn()
    empty = ExtractionResult(transcription="", ocr_text="", summary="", title="")
    await save_reel(conn, METADATA, empty)
    row = await find_by_url(conn, METADATA.source_url)
    assert row is not None
    assert row["content_type"] is None


async def test_update_extraction_only_affects_target_reel() -> None:
    conn = make_conn()
    empty = ExtractionResult(transcription="", ocr_text="", summary="", title="")
    reel_id = await save_reel(conn, METADATA, empty)

    other_metadata = ReelMetadata(
        source_url="https://www.instagram.com/reel/other999/",
        platform="instagram",
        author="other_author",
        posted_at=None,
        title="Other reel",
        caption=None,
        video_path=Path("/tmp/other999.mp4"),
        hashtags=[],
    )
    await save_reel(conn, other_metadata, empty)

    updated = ExtractionResult(
        transcription="only for first",
        ocr_text="only for first ocr",
        summary="only for first summary",
        title="Only For First",
        items=[],
    )
    await update_extraction(conn, reel_id, updated)

    other_row = await find_by_url(conn, other_metadata.source_url)
    assert other_row is not None
    assert other_row["transcription"] == ""


async def test_update_extraction_persists_items() -> None:
    conn = make_conn()
    empty = ExtractionResult(transcription="", ocr_text="", summary="", title="")
    reel_id = await save_reel(conn, METADATA, empty)
    updated = ExtractionResult(
        transcription="t",
        ocr_text="o",
        summary="s",
        title="t",
        items=[
            Item(name="Place A", item_type="place", description="Desc A"),
            Item(name="Place B", item_type="restaurant", description="Desc B"),
        ],
    )
    await update_extraction(conn, reel_id, updated)
    count = conn.execute(
        "SELECT COUNT(*) FROM items WHERE reel_id = ?", (reel_id,)
    ).fetchone()[0]
    assert count == 2


async def test_delete_by_url_removes_row() -> None:
    conn = make_conn()
    await save_reel(conn, METADATA, EXTRACTION)
    await delete_by_url(conn, METADATA.source_url)
    result = await find_by_url(conn, METADATA.source_url)
    assert result is None


async def test_delete_by_url_noop_on_missing_url() -> None:
    conn = make_conn()
    # Should not raise even if the URL was never saved
    await delete_by_url(conn, "https://www.instagram.com/reel/doesnotexist/")

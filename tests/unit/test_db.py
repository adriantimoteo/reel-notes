import sqlite3
import uuid
from pathlib import Path

import pytest

from storage.db import get_connection, init_db


def unique_memory_path() -> Path:
    """Return a unique named in-memory SQLite URI as a Path."""
    name = uuid.uuid4().hex
    return Path(f"file:{name}?mode=memory&cache=shared")


@pytest.fixture
def db_path() -> Path:
    return unique_memory_path()


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    init_db(db_path)
    c = get_connection(db_path)
    yield c
    c.close()


def test_reels_table_columns(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(reels)").fetchall()
    columns = {row["name"] for row in info}
    expected = {
        "id", "source_url", "platform", "author", "posted_at",
        "captured_at", "title", "caption", "transcription",
        "ocr_text", "summary", "vault_note_path",
    }
    assert expected == columns


def test_items_table_columns(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(items)").fetchall()
    columns = {row["name"] for row in info}
    expected = {"id", "reel_id", "name", "item_type", "description"}
    assert expected == columns


def test_duplicate_source_url_raises(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/1",)
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/1",)
        )


def test_cascade_delete_removes_items(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/2",)
    )
    reel_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO items (reel_id, name) VALUES (?, ?)", (reel_id, "Widget")
    )
    conn.commit()

    conn.execute("DELETE FROM reels WHERE id = ?", (reel_id,))
    conn.commit()

    items = conn.execute(
        "SELECT * FROM items WHERE reel_id = ?", (reel_id,)
    ).fetchall()
    assert items == []


def test_init_db_is_idempotent(db_path: Path) -> None:
    init_db(db_path)
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/3",)
    )
    conn.commit()

    init_db(db_path)

    row = conn.execute(
        "SELECT source_url FROM reels WHERE source_url = ?",
        ("https://example.com/reel/3",),
    ).fetchone()
    assert row is not None
    assert row["source_url"] == "https://example.com/reel/3"
    conn.close()

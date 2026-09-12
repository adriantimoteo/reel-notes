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
    c = get_connection(db_path)
    init_db(db_path)
    yield c
    c.close()


def test_reels_table_columns(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(reels)").fetchall()
    columns = {row["name"] for row in info}
    expected = {
        "id", "source_url", "platform", "author", "posted_at",
        "captured_at", "title", "caption", "transcription",
        "ocr_text", "summary", "vault_note_path", "content_type",
    }
    assert expected == columns


def test_items_table_does_not_exist(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'items'"
    ).fetchone()
    assert row is None


def test_init_db_drops_preexisting_items_table(db_path: Path) -> None:
    conn = get_connection(db_path)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, reel_id INTEGER, name TEXT)")
    conn.commit()

    init_db(db_path)

    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'items'"
    ).fetchone()
    assert row is None
    conn.close()


def test_duplicate_source_url_raises(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/1",)
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO reels (source_url) VALUES (?)", ("https://example.com/reel/1",)
        )


def test_init_db_is_idempotent(db_path: Path) -> None:
    conn = get_connection(db_path)
    init_db(db_path)
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

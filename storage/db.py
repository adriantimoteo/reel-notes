"""Database connection and setup."""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def get_connection(db_path: Path) -> sqlite3.Connection:
    logger.debug(f"opening connection to {db_path}")
    path_str = str(db_path)
    is_uri = path_str.startswith("file:")
    conn = sqlite3.connect(path_str, uri=is_uri)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    logger.debug("initialising database schema")
    with get_connection(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reels (
                id          INTEGER PRIMARY KEY,
                source_url  TEXT UNIQUE NOT NULL,
                platform    TEXT,
                author      TEXT,
                posted_at   TEXT,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
                title       TEXT,
                caption     TEXT,
                transcription TEXT,
                ocr_text    TEXT,
                summary     TEXT,
                vault_note_path TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id          INTEGER PRIMARY KEY,
                reel_id     INTEGER REFERENCES reels(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                item_type   TEXT,
                description TEXT
            )
        """)

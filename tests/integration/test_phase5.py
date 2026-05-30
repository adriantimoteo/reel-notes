"""Phase 5 integration tests: render, write, and DB vault path update."""

import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import handle_message
from output.writers import LocalFolderWriter
from pipeline.models import ExtractionResult, Item, ReelMetadata
from storage.db import get_connection, init_db
from storage.repository import find_by_url


def _make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    init_db(db_path)
    return get_connection(db_path)


def _make_bot() -> MagicMock:
    bot = MagicMock()
    sent_msg = MagicMock()
    sent_msg.message_id = 1
    bot.send_message = AsyncMock(return_value=sent_msg)
    bot.edit_message_text = AsyncMock()
    return bot


def _make_message(user_id: int, text: str) -> MagicMock:
    message = MagicMock()
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.text = text
    message.chat = MagicMock()
    message.chat.id = 100
    return message


ALLOWED_ID = 12345
REEL_URL = "https://instagram.com/reel/p5test1"

EXTRACTION = ExtractionResult(
    transcription="full transcription for phase five",
    ocr_text="visible on-screen text for phase five",
    summary="A short summary of the reel content for phase five testing.",
    title="Phase Five Test Reel",
    items=[
        Item(name="Shibuya Ramen", item_type="restaurant", description="Great ramen spot."),
        Item(name="Harajuku Park", item_type="place", description="Famous park area."),
    ],
)


def _make_fetch_result(video_path: Path, url_slug: str = "p5test1") -> ReelMetadata:
    return ReelMetadata(
        source_url=f"instagram.com/reel/{url_slug}",
        platform="instagram",
        author="tester",
        posted_at=datetime(2024, 6, 1),
        title="Phase 5 reel",
        caption="Testing render and write wiring",
        video_path=video_path,
    )


# --- AC1: Full pipeline writes note to disk ---

async def test_full_pipeline_writes_note(tmp_path: Path) -> None:
    conn = _make_conn()
    bot = _make_bot()
    vault_writer = LocalFolderWriter(tmp_path, "notes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path)
    msg = _make_message(ALLOWED_ID, REEL_URL)

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", vault_writer), \
         patch("pipeline.orchestrator.config") as mock_orch_cfg, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        mock_orch_cfg.VAULT_PATH = tmp_path
        await handle_message(msg)

    notes_dir = tmp_path / "notes"
    written_files = list(notes_dir.glob("*.md"))
    assert written_files, f"Expected at least one .md file in {notes_dir}"
    assert written_files[0].read_text(encoding="utf-8"), "Expected non-empty note content"


# --- AC2: DB has vault_note_path after successful run ---

async def test_db_has_vault_note_path(tmp_path: Path) -> None:
    conn = _make_conn()
    bot = _make_bot()
    vault_writer = LocalFolderWriter(tmp_path, "notes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path, url_slug="p5db1")
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p5db1")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", vault_writer), \
         patch("pipeline.orchestrator.config") as mock_orch_cfg, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        mock_orch_cfg.VAULT_PATH = tmp_path
        await handle_message(msg)

    row = await find_by_url(conn, "instagram.com/reel/p5db1")
    assert row is not None, "Expected reel row in DB"
    assert row["vault_note_path"], f"Expected non-empty vault_note_path, got: {row['vault_note_path']}"


# --- AC3: Final status contains "saved" and filename ---

async def test_final_status_contains_saved_and_filename(tmp_path: Path) -> None:
    conn = _make_conn()
    bot = _make_bot()
    vault_writer = LocalFolderWriter(tmp_path, "notes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path, url_slug="p5status1")
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p5status1")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", vault_writer), \
         patch("pipeline.orchestrator.config") as mock_orch_cfg, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        mock_orch_cfg.VAULT_PATH = tmp_path
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    last_call = calls[-1]
    assert "saved" in last_call, f"Expected 'saved' in last status call: {last_call}"
    assert ".md" in last_call, f"Expected filename (.md) in last status call: {last_call}"


# --- AC4: Save failure is surfaced in status ---

async def test_save_failure_surfaced_in_status(tmp_path: Path) -> None:
    conn = _make_conn()
    bot = _make_bot()
    vault_writer = LocalFolderWriter(tmp_path, "notes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path, url_slug="p5fail1")
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p5fail1")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", vault_writer), \
         patch("pipeline.orchestrator.config") as mock_orch_cfg, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch.object(vault_writer, "write", side_effect=Exception("disk full")):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        mock_orch_cfg.VAULT_PATH = tmp_path
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]
    failure_calls = [c for c in calls if "disk full" in c]
    assert failure_calls, f"Expected 'disk full' in status calls, got: {calls}"


# --- AC5: Status sequence is downloading → extracting → saved ---

async def test_status_sequence(tmp_path: Path) -> None:
    conn = _make_conn()
    bot = _make_bot()
    vault_writer = LocalFolderWriter(tmp_path, "notes")

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        video_path = Path(f.name)

    fetch_result = _make_fetch_result(video_path, url_slug="p5seq1")
    msg = _make_message(ALLOWED_ID, "https://instagram.com/reel/p5seq1")

    with patch("bot.handlers.config") as mock_cfg, \
         patch("bot.handlers._bot", bot), \
         patch("bot.handlers._conn", conn), \
         patch("bot.handlers._vault_writer", vault_writer), \
         patch("pipeline.orchestrator.config") as mock_orch_cfg, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=fetch_result)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)):
        mock_cfg.TELEGRAM_ALLOWED_USER_ID = ALLOWED_ID
        mock_orch_cfg.VAULT_PATH = tmp_path
        await handle_message(msg)

    calls = [call[0][0] for call in bot.edit_message_text.call_args_list]

    downloading_idx = next((i for i, c in enumerate(calls) if "downloading" in c), None)
    extracting_idx = next((i for i, c in enumerate(calls) if "extracting" in c), None)
    saved_idx = next((i for i, c in enumerate(calls) if "saved" in c), None)

    assert downloading_idx is not None, f"Expected 'downloading…' in calls: {calls}"
    assert extracting_idx is not None, f"Expected 'extracting…' in calls: {calls}"
    assert saved_idx is not None, f"Expected 'saved' in calls: {calls}"
    assert downloading_idx < extracting_idx < saved_idx, (
        f"Expected sequence downloading→extracting→saved, got indices: "
        f"{downloading_idx}, {extracting_idx}, {saved_idx}"
    )

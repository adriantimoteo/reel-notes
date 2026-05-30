"""Tests for the pipeline exception hierarchy and orchestrator error dispatch."""

import sqlite3
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.exceptions import (
    DownloadError,
    DurationCapExceeded,
    ExtractionError,
    ReelCaptureError,
    StorageError,
    UnsupportedPlatformError,
    VaultWriteError,
)
from pipeline.models import ExtractionResult, Item, ReelMetadata
from pipeline.orchestrator import run
from bot.status import StatusMessage
from storage.db import get_connection, init_db


# --- AC2: cause preserved ---

def test_download_error_preserves_cause() -> None:
    cause = RuntimeError("network timeout")
    exc = DownloadError(url="https://x.com", cause=cause)
    assert exc.cause is cause
    assert exc.url == "https://x.com"


def test_extraction_error_preserves_cause() -> None:
    cause = ValueError("bad JSON")
    exc = ExtractionError(cause=cause)
    assert exc.cause is cause


def test_storage_error_preserves_cause() -> None:
    cause = sqlite3.IntegrityError("UNIQUE constraint failed")
    exc = StorageError(cause=cause)
    assert exc.cause is cause


def test_vault_write_error_preserves_cause_and_path() -> None:
    cause = OSError("disk full")
    exc = VaultWriteError(path="notes/foo.md", cause=cause)
    assert exc.cause is cause
    assert exc.path == "notes/foo.md"


# --- AC3: all are subclasses of ReelCaptureError ---

@pytest.mark.parametrize("exc_cls,kwargs", [
    (UnsupportedPlatformError, {"url": "https://x.com"}),
    (DurationCapExceeded, {"duration": 300, "cap": 120}),
    (DownloadError, {"url": "https://x.com", "cause": Exception("err")}),
    (ExtractionError, {"cause": Exception("err")}),
    (StorageError, {"cause": Exception("err")}),
    (VaultWriteError, {"path": "foo.md", "cause": Exception("err")}),
])
def test_all_are_subclass_of_reel_capture_error(exc_cls, kwargs) -> None:
    exc = exc_cls(**kwargs)
    assert isinstance(exc, ReelCaptureError)


# --- AC1: dispatch produces the expected status message fragment per exception type ---
# These tests verify the isinstance branch chain in orchestrator.run.
# Each exception is raised at the appropriate pipeline stage so the orchestrator
# wraps it (or passes it through) correctly.


# --- Orchestrator dispatch integration ---

def _make_conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    conn = get_connection(db_path)
    init_db(db_path)
    return conn


def _make_status() -> tuple[StatusMessage, list[str]]:
    updates: list[str] = []
    status = MagicMock(spec=StatusMessage)
    status.update = AsyncMock(side_effect=lambda text: updates.append(text))
    return status, updates


def _make_metadata(tmp_path: Path) -> ReelMetadata:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    return ReelMetadata(
        source_url="https://instagram.com/reel/test",
        platform="instagram",
        author="tester",
        posted_at=datetime(2024, 1, 1),
        title="Test",
        caption=None,
        video_path=video,
    )


EXTRACTION = ExtractionResult(
    transcription="t", ocr_text="o", summary="s", title="Test Title"
)


async def test_download_exception_produces_download_failed(tmp_path: Path) -> None:
    conn = _make_conn()
    status, updates = _make_status()

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(side_effect=RuntimeError("net err"))), \
         patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)):
        await run("https://instagram.com/reel/test", status, conn, MagicMock())

    assert any("download failed" in u for u in updates), f"Got: {updates}"


async def test_extraction_exception_produces_extraction_failed(tmp_path: Path) -> None:
    conn = _make_conn()
    status, updates = _make_status()
    metadata = _make_metadata(tmp_path)

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=RuntimeError("quota"))), \
         patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)):
        await run("https://instagram.com/reel/test", status, conn, MagicMock())

    assert any("extraction failed" in u for u in updates), f"Got: {updates}"


async def test_vault_write_exception_produces_vault_write_failed(tmp_path: Path) -> None:
    conn = _make_conn()
    status, updates = _make_status()
    metadata = _make_metadata(tmp_path)
    vault_writer = MagicMock()
    vault_writer.write.side_effect = OSError("disk full")

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()):
        await run("https://instagram.com/reel/test", status, conn, vault_writer)

    assert any("vault write failed" in u for u in updates), f"Got: {updates}"


async def test_storage_exception_produces_save_failed(tmp_path: Path) -> None:
    conn = _make_conn()
    status, updates = _make_status()
    metadata = _make_metadata(tmp_path)
    note = tmp_path / "note.md"
    note.write_text("content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = note

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock(side_effect=Exception("db err"))), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run("https://instagram.com/reel/test", status, conn, vault_writer)

    assert any("save failed" in u for u in updates), f"Got: {updates}"


# --- AC4: unexpected exception falls through to generic message ---

async def test_unexpected_exception_produces_generic_message() -> None:
    conn = _make_conn()
    status, updates = _make_status()

    # save_reel is outside inner try/except blocks — a RuntimeError propagates to outer handler
    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=MagicMock())), \
         patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(side_effect=RuntimeError("boom"))):
        await run("https://instagram.com/reel/test", status, conn, MagicMock())

    assert any("pipeline error" in u for u in updates), f"Got: {updates}"

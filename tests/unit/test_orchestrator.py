"""Unit tests for orchestrator force-reprocess path (T2.1)."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from bot.status import StatusMessage
from pipeline.models import ExtractionResult, ReelMetadata
from pipeline.orchestrator import run


URL = "https://instagram.com/reel/test123"


def _make_status() -> tuple[StatusMessage, list[str]]:
    updates: list[str] = []
    status = MagicMock(spec=StatusMessage)
    status.update = AsyncMock(side_effect=lambda text: updates.append(text))
    return status, updates


def _make_metadata(tmp_path: Path) -> ReelMetadata:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"fake")
    return ReelMetadata(
        source_url=URL,
        platform="instagram",
        author="tester",
        posted_at=datetime(2024, 1, 1),
        title="Test Reel",
        caption=None,
        video_path=video,
    )


EXTRACTION = ExtractionResult(
    transcription="t", ocr_text="o", summary="s", title="Test Title"
)


async def test_run_does_not_dedup_when_force_true(tmp_path: Path) -> None:
    """With force=True, the pipeline proceeds even when find_by_url returns an existing row."""
    metadata = _make_metadata(tmp_path)
    status, updates = _make_status()
    note = tmp_path / "note.md"
    note.write_text("content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = note

    existing_row = {"vault_note_path": None}

    with patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=existing_row)), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.delete_by_url", AsyncMock()), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock()), \
         patch("pipeline.orchestrator.renderer.generate_filename", return_value="note.md"), \
         patch("pipeline.orchestrator.renderer.render", return_value="# content"), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run(URL, status, MagicMock(), vault_writer, force=True)

    assert not any("already captured" in u for u in updates), "force=True should not trigger dedup"
    assert any("saved" in u for u in updates), "pipeline should have completed"


async def test_run_checks_dedup_when_force_false(tmp_path: Path) -> None:
    """With force=False (default), find_by_url must be called."""
    status, _ = _make_status()

    with patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=None)) as mock_find, \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(side_effect=RuntimeError("stop early"))), \
         patch("pipeline.orchestrator.repository.delete_by_url", AsyncMock()):
        await run(URL, status, MagicMock(), MagicMock(), force=False)

    mock_find.assert_called_once()


async def test_run_deletes_existing_record_when_force_true_and_url_exists(tmp_path: Path) -> None:
    """With force=True, delete_by_url must be called after download but before save_reel."""
    metadata = _make_metadata(tmp_path)
    status, _ = _make_status()
    note = tmp_path / "note.md"
    note.write_text("content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = note

    call_order: list[str] = []

    async def mock_fetch(url: str) -> ReelMetadata:
        call_order.append("fetch")
        return metadata

    async def mock_delete(conn, url: str) -> None:
        call_order.append("delete_by_url")

    async def mock_save_reel(conn, meta, extraction) -> int:
        call_order.append("save_reel")
        return 1

    with patch("pipeline.orchestrator.downloader.fetch", side_effect=mock_fetch), \
         patch("pipeline.orchestrator.repository.delete_by_url", side_effect=mock_delete), \
         patch("pipeline.orchestrator.repository.save_reel", side_effect=mock_save_reel), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock()), \
         patch("pipeline.orchestrator.renderer.generate_filename", return_value="note.md"), \
         patch("pipeline.orchestrator.renderer.render", return_value="# content"), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run(URL, status, MagicMock(), vault_writer, force=True)

    assert "delete_by_url" in call_order, "delete_by_url was never called"
    assert "save_reel" in call_order, "save_reel was never called"
    delete_idx = call_order.index("delete_by_url")
    fetch_idx = call_order.index("fetch")
    save_idx = call_order.index("save_reel")
    assert fetch_idx < delete_idx, "delete_by_url must happen after fetch"
    assert delete_idx < save_idx, "delete_by_url must happen before save_reel"


async def test_type_hint_passed_to_extractor(tmp_path: Path) -> None:
    """With force=True and type_hint='tutorial', extractor.extract is called with type_hint='tutorial'."""
    metadata = _make_metadata(tmp_path)
    status, _ = _make_status()
    note = tmp_path / "note.md"
    note.write_text("content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = note

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)) as mock_extract, \
         patch("pipeline.orchestrator.repository.delete_by_url", AsyncMock()), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock()), \
         patch("pipeline.orchestrator.renderer.generate_filename", return_value="note.md"), \
         patch("pipeline.orchestrator.renderer.render", return_value="# content"), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run(URL, status, MagicMock(), vault_writer, force=True, type_hint="tutorial")

    mock_extract.assert_called_once_with(metadata, type_hint="tutorial")


async def test_run_deletes_old_note_when_force_true(tmp_path: Path) -> None:
    """When force=True and existing record has vault_note_path, the old file is deleted."""
    metadata = _make_metadata(tmp_path)
    status, _ = _make_status()
    old_note = tmp_path / "old-note.md"
    old_note.write_text("old content")
    new_note = tmp_path / "new-note.md"
    new_note.write_text("new content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = new_note

    existing_row = {"vault_note_path": "old-note.md"}

    with patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=existing_row)), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.delete_by_url", AsyncMock()), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock()), \
         patch("pipeline.orchestrator.renderer.generate_filename", return_value="new-note.md"), \
         patch("pipeline.orchestrator.renderer.render", return_value="# content"), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run(URL, status, MagicMock(), vault_writer, force=True)

    assert not old_note.exists(), "old note file should have been deleted"


async def test_run_no_file_deletion_when_note_path_is_null(tmp_path: Path) -> None:
    """When force=True and vault_note_path is NULL, no file deletion is attempted."""
    metadata = _make_metadata(tmp_path)
    status, _ = _make_status()
    note = tmp_path / "note.md"
    note.write_text("content")
    vault_writer = MagicMock()
    vault_writer.write.return_value = note

    existing_row = {"vault_note_path": None}

    with patch("pipeline.orchestrator.repository.find_by_url", AsyncMock(return_value=existing_row)), \
         patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=metadata)), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(return_value=EXTRACTION)), \
         patch("pipeline.orchestrator.repository.delete_by_url", AsyncMock()), \
         patch("pipeline.orchestrator.repository.save_reel", AsyncMock(return_value=1)), \
         patch("pipeline.orchestrator.repository.update_extraction", AsyncMock()), \
         patch("pipeline.orchestrator.repository.update_vault_path", AsyncMock()), \
         patch("pipeline.orchestrator.renderer.generate_filename", return_value="note.md"), \
         patch("pipeline.orchestrator.renderer.render", return_value="# content"), \
         patch("pipeline.orchestrator.config") as mock_cfg:
        mock_cfg.VAULT_PATH = tmp_path
        await run(URL, status, MagicMock(), vault_writer, force=True)

    assert note.exists(), "note should not have been touched"

from pathlib import Path

import pytest

from output.writers import LocalFolderWriter, VaultWriter


def test_write_creates_file_with_content(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "notes")
    writer.write("note.md", "# Hello")
    assert (tmp_path / "notes" / "note.md").read_text(encoding="utf-8") == "# Hello"


def test_write_creates_missing_subdir(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "deep/nested/dir")
    writer.write("file.md", "content")
    assert (tmp_path / "deep" / "nested" / "dir" / "file.md").exists()


def test_write_overwrites_existing_file(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "notes")
    writer.write("note.md", "first")
    writer.write("note.md", "second")
    assert (tmp_path / "notes" / "note.md").read_text(encoding="utf-8") == "second"


def test_write_returns_absolute_path(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "notes")
    result = writer.write("note.md", "# Hello")
    assert isinstance(result, Path)
    assert result.is_absolute()


def test_local_folder_writer_is_vault_writer(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "notes")
    assert isinstance(writer, VaultWriter)


def test_write_returns_correct_path(tmp_path: Path) -> None:
    writer = LocalFolderWriter(tmp_path, "notes")
    result = writer.write("note.md", "# Hello")
    assert result == tmp_path / "notes" / "note.md"

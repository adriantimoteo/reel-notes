"""Tests for cleanup_temp_dir."""

from pathlib import Path

from main import cleanup_temp_dir


# --- AC1: mp4 files deleted, txt untouched, returns correct count ---

def test_deletes_video_files_and_returns_count(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"v1")
    (tmp_path / "b.mp4").write_bytes(b"v2")
    (tmp_path / "notes.txt").write_text("keep me")

    count = cleanup_temp_dir(tmp_path)

    assert count == 2
    assert not (tmp_path / "a.mp4").exists()
    assert not (tmp_path / "b.mp4").exists()
    assert (tmp_path / "notes.txt").exists()


def test_deletes_all_video_extensions(tmp_path: Path) -> None:
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.webm").write_bytes(b"x")
    (tmp_path / "c.mkv").write_bytes(b"x")
    (tmp_path / "d.m4v").write_bytes(b"x")

    count = cleanup_temp_dir(tmp_path)

    assert count == 4
    assert not any(tmp_path.glob("*.mp4"))
    assert not any(tmp_path.glob("*.webm"))
    assert not any(tmp_path.glob("*.mkv"))
    assert not any(tmp_path.glob("*.m4v"))


def test_deletes_image_and_audio_extensions_from_carousel_slides(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"x")
    (tmp_path / "b.jpeg").write_bytes(b"x")
    (tmp_path / "c.png").write_bytes(b"x")
    (tmp_path / "d.webp").write_bytes(b"x")
    (tmp_path / "e.m4a").write_bytes(b"x")
    (tmp_path / "f.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("keep me")

    count = cleanup_temp_dir(tmp_path)

    assert count == 6
    assert not any(tmp_path.glob("*.jpg"))
    assert not any(tmp_path.glob("*.jpeg"))
    assert not any(tmp_path.glob("*.png"))
    assert not any(tmp_path.glob("*.webp"))
    assert not any(tmp_path.glob("*.m4a"))
    assert not any(tmp_path.glob("*.mp3"))
    assert (tmp_path / "notes.txt").exists()


# --- AC2: empty directory returns 0 ---

def test_empty_directory_returns_zero(tmp_path: Path) -> None:
    assert cleanup_temp_dir(tmp_path) == 0


# --- AC3: non-existent directory is created and returns 0 ---

def test_creates_missing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "does" / "not" / "exist"
    assert not missing.exists()

    count = cleanup_temp_dir(missing)

    assert count == 0
    assert missing.exists()
    assert missing.is_dir()

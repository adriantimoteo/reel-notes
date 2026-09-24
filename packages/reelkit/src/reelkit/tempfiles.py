"""Housekeeping for the download temp dir."""

from pathlib import Path

_MEDIA_GLOBS = (
    "*.mp4", "*.webm", "*.mkv", "*.m4v",
    "*.jpg", "*.jpeg", "*.png", "*.webp",
    "*.m4a", "*.mp3",
)


def cleanup_temp_dir(temp_dir: Path) -> int:
    """Delete stale video files. Returns count of files removed."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for ext in _MEDIA_GLOBS:
        for f in temp_dir.glob(ext):
            f.unlink(missing_ok=True)
            removed += 1
    return removed

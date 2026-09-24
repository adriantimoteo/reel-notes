"""Custom exceptions for the pipeline.

The download/extraction errors are shared via reelkit and re-exported here;
storage and vault errors are specific to this app.
"""

from reelkit.exceptions import (
    DownloadError,
    DurationCapExceeded,
    ExtractionError,
    ReelCaptureError,
    UnsupportedCarouselError,
    UnsupportedPlatformError,
)

__all__ = [
    "DownloadError",
    "DurationCapExceeded",
    "ExtractionError",
    "ReelCaptureError",
    "StorageError",
    "UnsupportedCarouselError",
    "UnsupportedPlatformError",
    "VaultWriteError",
]


class StorageError(ReelCaptureError):
    """SQLite write failed."""
    def __init__(self, cause: Exception) -> None:
        super().__init__(f"storage failed: {cause}")
        self.cause = cause


class VaultWriteError(ReelCaptureError):
    """Filesystem write to vault failed."""
    def __init__(self, path: str, cause: Exception) -> None:
        super().__init__(f"vault write failed for {path}: {cause}")
        self.path = path
        self.cause = cause

"""Custom exceptions for the pipeline."""


class ReelCaptureError(Exception):
    """Base for all pipeline errors."""


class UnsupportedPlatformError(ReelCaptureError):
    def __init__(self, url: str) -> None:
        super().__init__(f"unsupported URL: {url}")
        self.url = url


class DurationCapExceeded(ReelCaptureError):
    def __init__(self, duration: int, cap: int) -> None:
        super().__init__(f"video is {duration}s, limit is {cap}s")
        self.duration = duration
        self.cap = cap


class DownloadError(ReelCaptureError):
    """yt-dlp failed for any reason other than duration."""
    def __init__(self, url: str, cause: Exception) -> None:
        super().__init__(f"download failed for {url}: {cause}")
        self.url = url
        self.cause = cause


class ExtractionError(ReelCaptureError):
    """Gemini call failed or returned unparseable response."""
    def __init__(self, cause: Exception) -> None:
        super().__init__(f"extraction failed: {cause}")
        self.cause = cause


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

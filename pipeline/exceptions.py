"""Custom exceptions for the pipeline."""


class ReelCaptureError(Exception):
    pass


class UnsupportedPlatformError(ReelCaptureError):
    def __init__(self, url: str) -> None:
        super().__init__(f"unsupported URL: {url}")
        self.url = url


class DurationCapExceeded(ReelCaptureError):
    def __init__(self, duration: int, cap: int) -> None:
        super().__init__(f"video is {duration}s, limit is {cap}s")
        self.duration = duration
        self.cap = cap

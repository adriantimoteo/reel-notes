"""Custom exceptions for the pipeline."""


class ReelCaptureError(Exception):
    pass


class UnsupportedPlatformError(ReelCaptureError):
    def __init__(self, url: str) -> None:
        super().__init__(f"unsupported URL: {url}")
        self.url = url

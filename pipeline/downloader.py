"""Video download logic — wires this app's config into reelkit.fetch."""

import config
from reelkit import fetch as _reelkit_fetch
from reelkit.fetch import FetchSettings, normalize_metadata
from reelkit.models import ReelMetadata
from reelkit.urls import canonicalize, detect_platform, resolve_canonical_url

__all__ = [
    "canonicalize",
    "detect_platform",
    "fetch",
    "fetch_settings",
    "normalize_metadata",
    "resolve_canonical_url",
]


def fetch_settings(max_duration: int | None = None) -> FetchSettings:
    """Builds FetchSettings from config at call time. `max_duration` overrides the
    configured cap (used by /force)."""
    return FetchSettings(
        temp_dir=config.DOWNLOAD_TEMP_DIR,
        max_duration=max_duration if max_duration is not None else config.MAX_VIDEO_DURATION_SECONDS,
        cookies_file=config.YTDLP_COOKIES_FILE,
        cookies_from_browser=config.YTDLP_COOKIES_FROM_BROWSER,
    )


async def fetch(url: str, max_duration: int | None = None) -> ReelMetadata:
    return await _reelkit_fetch.fetch(url, fetch_settings(max_duration))

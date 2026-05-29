"""Video download logic."""

import logging
import urllib.parse

import yt_dlp

import config
from pipeline.exceptions import DurationCapExceeded, UnsupportedPlatformError

logger = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    """Returns 'instagram', 'tiktok', or 'youtube'. Raises UnsupportedPlatformError for anything else."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path

    if host == "instagram.com":
        if any(path.startswith(prefix) for prefix in ("/reel/", "/p/", "/tv/")):
            return "instagram"
    elif host in ("tiktok.com", "vm.tiktok.com"):
        return "tiktok"
    elif host == "youtube.com":
        if path.startswith("/shorts/") or path.startswith("/watch"):
            return "youtube"
    elif host == "youtu.be":
        return "youtube"

    raise UnsupportedPlatformError(url)


def canonicalize(url: str, platform: str) -> str:
    """Strips tracking query params. Preserves YouTube watch?v= param (it is the video ID, not tracking)."""
    parsed = urllib.parse.urlparse(url)

    if platform == "youtube" and parsed.path.startswith("/watch"):
        query_params = urllib.parse.parse_qs(parsed.query)
        kept = {"v": query_params["v"]} if "v" in query_params else {}
        new_query = urllib.parse.urlencode(kept, doseq=True)
        canonical = parsed._replace(query=new_query, fragment="")
    else:
        canonical = parsed._replace(query="", fragment="")

    return urllib.parse.urlunparse(canonical)


def _fetch_info(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration", 0)
    if duration > config.MAX_VIDEO_DURATION_SECONDS:
        raise DurationCapExceeded(duration=duration, cap=config.MAX_VIDEO_DURATION_SECONDS)
    info.setdefault("tags", [])
    logger.debug("fetched info for %s: duration=%ss", url, duration)
    return info

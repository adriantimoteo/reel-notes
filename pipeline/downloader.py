"""Video download logic."""

import logging
import urllib.parse

from pipeline.exceptions import UnsupportedPlatformError

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
        canonical = parsed._replace(query=new_query)
    else:
        canonical = parsed._replace(query="", fragment="")

    return urllib.parse.urlunparse(canonical)

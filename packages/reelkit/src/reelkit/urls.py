"""Reel URL detection, platform identification, and canonicalization."""

import asyncio
import logging
import urllib.parse
import urllib.request

from reelkit.exceptions import UnsupportedCarouselError, UnsupportedPlatformError

logger = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    """Returns 'instagram', 'tiktok', or 'youtube'. Raises UnsupportedPlatformError for anything else."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path

    if host == "instagram.com":
        if any(path.startswith(prefix) for prefix in ("/reel/", "/p/", "/tv/")):
            return "instagram"
    elif host in ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com"):
        return "tiktok"
    elif host == "youtube.com":
        if path.startswith("/shorts/") or path.startswith("/watch"):
            return "youtube"
        if path.startswith("/post/"):
            # Best-effort: YouTube's 2026 image-carousel Shorts format appears to live
            # under this path, but no real example has been seen yet to confirm the
            # exact shape. Revisit once one actually comes through.
            raise UnsupportedCarouselError(url)
    elif host == "youtu.be":
        return "youtube"

    raise UnsupportedPlatformError(url)


def is_tiktok_photo_post(canonical_url: str) -> bool:
    return "/photo/" in urllib.parse.urlparse(canonical_url).path


def is_instagram_post_path(canonical_url: str) -> bool:
    return urllib.parse.urlparse(canonical_url).path.startswith("/p/")


_TIKTOK_SHORTLINK_HOSTS = ("vm.tiktok.com", "vt.tiktok.com")


def is_tiktok_shortlink(canonical_url: str) -> bool:
    host = urllib.parse.urlparse(canonical_url).netloc.lower().removeprefix("www.")
    return host in _TIKTOK_SHORTLINK_HOSTS


def _resolve_tiktok_shortlink(url: str) -> str:
    """vm./vt.tiktok.com links redirect to the real /video/<id> or /photo/<id> URL.
    We need the resolved form up front to route photo-mode posts correctly — yt-dlp
    only reveals the real path after attempting extraction and failing."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.url


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


async def resolve_canonical_url(url: str) -> tuple[str, str]:
    """Returns (canonical_url, platform). The only network call this makes is an
    optional HEAD request to resolve a TikTok shortlink — safe to call ahead of a
    full fetch() so callers can key DB lookups on the same URL fetch() will end up
    storing, instead of on whatever raw/shortlink form the caller passed in."""
    platform = detect_platform(url)
    canonical = canonicalize(url, platform)

    if platform == "tiktok" and is_tiktok_shortlink(canonical):
        try:
            resolved = await asyncio.to_thread(_resolve_tiktok_shortlink, canonical)
            canonical = canonicalize(resolved, platform)
        except Exception as e:
            logger.warning("failed to resolve TikTok short link %s: %s", canonical, e)

    return canonical, platform

"""Video download logic."""

import asyncio
import logging
import urllib.parse
from datetime import datetime
from pathlib import Path

import yt_dlp

import config
from pipeline.exceptions import DurationCapExceeded, UnsupportedPlatformError
from pipeline.models import ReelMetadata

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


def _download(url: str, temp_dir: Path) -> Path:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
        "format": "mp4/bestvideo+bestaudio/best",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    filename = f"{info['id']}.{info['ext']}"
    return temp_dir / filename


def normalize_metadata(info: dict, video_path: Path, platform: str, source_url: str) -> ReelMetadata:
    upload_date = info.get("upload_date")
    posted_at = datetime.strptime(upload_date, "%Y%m%d") if upload_date else None
    return ReelMetadata(
        source_url=source_url,
        platform=platform,
        author=info.get("uploader") or info.get("channel"),
        posted_at=posted_at,
        title=info.get("title"),
        caption=info.get("description"),
        video_path=video_path,
        hashtags=info.get("tags", []),
    )


async def fetch(url: str) -> ReelMetadata:
    platform = detect_platform(url)
    canonical = canonicalize(url, platform)
    info = await asyncio.to_thread(_fetch_info, canonical)
    video_path = await asyncio.to_thread(_download, canonical, config.DOWNLOAD_TEMP_DIR)
    metadata = normalize_metadata(info, video_path, platform, canonical)
    logger.info("fetched metadata for %s", canonical)
    return metadata

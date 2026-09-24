"""Reel download: yt-dlp for videos, gallery-dl for TikTok photo posts and Instagram carousels."""

import logging
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import gallery_dl.config as gallery_dl_config
import gallery_dl.extractor.tiktok as gallery_dl_tiktok
import gallery_dl.job as gallery_dl_job
import yt_dlp

from reelkit.exceptions import DurationCapExceeded, UnsupportedPlatformError
from reelkit.models import ReelMetadata
from reelkit.retry import call_with_retry
from reelkit.urls import is_instagram_post_path, is_tiktok_photo_post, resolve_canonical_url

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchSettings:
    """Everything fetch() needs, passed per call so different callers (or different
    groups of one multi-tenant caller) can use different caps and cookie sources."""

    temp_dir: Path
    max_duration: int = 120
    cookies_file: Path | None = None
    cookies_from_browser: str | None = None


def _patched_tiktok_post_probe_url(self: gallery_dl_tiktok.TiktokPostExtractor) -> dict:
    """gallery-dl's TiktokPostExtractor.posts() always probes the /video/<id> URL
    first, even for a photo post, relying on a fallback that only triggers if that
    probe succeeds with the wrong shape — not if it gets rejected outright (TikTok
    has been observed 403-ing that /video/ probe for photo-only post ids). Since we
    already know which form the URL actually is, probe the correct one directly."""
    user, post_id = self.groups
    kind = "photo" if "/photo/" in self.url else "video"
    url = f"{self.root}/@{user or ''}/{kind}/{post_id}"
    return {url: None}


gallery_dl_tiktok.TiktokPostExtractor.posts = _patched_tiktok_post_probe_url

DOWNLOAD_RETRY_ATTEMPTS = 3
DOWNLOAD_RETRY_BASE_DELAY = 2.0


def _is_retryable_download_error(e: Exception) -> bool:
    """DurationCapExceeded/UnsupportedPlatformError are deterministic — retrying won't help."""
    return not isinstance(e, (DurationCapExceeded, UnsupportedPlatformError))


def _sanitize_cookies_file(source: Path) -> Path:
    """Returns path to a cleaned copy of a Netscape cookies.txt with malformed lines removed.

    Browser exporters (and Edge in particular) sometimes include cookies with
    empty values. Python's http.cookiejar rejects those lines, so we strip them
    and write a sibling file that yt-dlp can load cleanly.
    """
    dest = source.with_stem(source.stem + "_clean")
    with source.open(encoding="utf-8", errors="replace") as f_in, \
         dest.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            stripped = line.rstrip("\n\r")
            if stripped.startswith("#") or stripped == "":
                f_out.write(line)
                continue
            fields = stripped.split("\t")
            if len(fields) == 7 and fields[6] != "":
                # Netscape format requires: domain starts with '.' iff flag col is TRUE
                initial_dot = fields[0].startswith(".")
                domain_flag = fields[1].upper() == "TRUE"
                if initial_dot == domain_flag:
                    f_out.write(line)
                else:
                    logger.debug("cookies: dropped malformed line: %s", stripped[:80])
            else:
                logger.debug("cookies: dropped malformed line: %s", stripped[:80])
    return dest


def _apply_cookies(ydl_opts: dict, settings: FetchSettings) -> dict:
    """Adds cookie auth to yt-dlp opts. Instagram (and sometimes others) reject
    anonymous requests with an empty media response, so pass browser cookies or a
    cookies.txt file when configured."""
    if settings.cookies_from_browser:
        # yt-dlp expects a tuple: (browser, profile, keyring, container)
        ydl_opts["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    elif settings.cookies_file:
        clean = _sanitize_cookies_file(settings.cookies_file)
        ydl_opts["cookiefile"] = str(clean)
    return ydl_opts


def _apply_gallery_dl_cookies(settings: FetchSettings) -> None:
    """Mirrors _apply_cookies, but for gallery-dl's global config (used for the
    TikTok photo-post and Instagram carousel fetch paths, which bypass yt-dlp)."""
    if settings.cookies_from_browser:
        gallery_dl_config.set(("extractor",), "cookies", (settings.cookies_from_browser,))
    elif settings.cookies_file:
        clean = _sanitize_cookies_file(settings.cookies_file)
        gallery_dl_config.set(("extractor",), "cookies", str(clean))


def _download_media_url(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        dest.write_bytes(response.read())


def _run_carousel_job(url: str) -> gallery_dl_job.DataJob:
    job = gallery_dl_job.DataJob(url, file=None)
    job.run()
    if job.exception is not None:
        raise job.exception
    if not job.data_post:
        raise RuntimeError(f"gallery-dl returned no post data for {url}")
    return job


def _fetch_tiktok_photo_post(url: str, temp_dir: Path) -> ReelMetadata:
    job = _run_carousel_job(url)
    post = job.data_post[0]
    post_id = post.get("id") or "tiktok_photo"

    image_paths: list[Path] = []
    audio_path: Path | None = None
    for i, (media_url, meta) in enumerate(zip(job.data_urls, job.data_meta), start=1):
        ext = meta.get("extension") or "bin"
        if meta.get("type") == "audio":
            audio_path = temp_dir / f"{post_id}_audio.{ext}"
            _download_media_url(media_url, audio_path)
        else:
            dest = temp_dir / f"{post_id}_{i}.{ext}"
            _download_media_url(media_url, dest)
            image_paths.append(dest)

    if not image_paths:
        raise RuntimeError(f"no image slides found for {url}")

    author = (post.get("author") or {}).get("uniqueId")
    create_time = post.get("createTime")
    posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc) if create_time else None
    hashtags = [h["hashtagName"] for h in post.get("textExtra", []) if h.get("hashtagName")]

    return ReelMetadata(
        source_url=url,
        platform="tiktok",
        author=author,
        posted_at=posted_at,
        title=None,
        caption=post.get("desc"),
        image_paths=image_paths,
        audio_path=audio_path,
        hashtags=hashtags,
    )


def _fetch_instagram_carousel(url: str, temp_dir: Path) -> ReelMetadata:
    job = _run_carousel_job(url)
    post = job.data_post[0]
    post_id = post.get("post_id") or "instagram_post"

    image_paths: list[Path] = []
    for i, (media_url, meta) in enumerate(zip(job.data_urls, job.data_meta), start=1):
        ext = meta.get("extension") or "bin"
        dest = temp_dir / f"{post_id}_{i}.{ext}"
        _download_media_url(media_url, dest)
        image_paths.append(dest)

    if not image_paths:
        raise RuntimeError(f"no media found for {url}")

    posted_at = post.get("date")
    if isinstance(posted_at, datetime) and posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=timezone.utc)

    return ReelMetadata(
        source_url=url,
        platform="instagram",
        author=post.get("username"),
        posted_at=posted_at,
        title=None,
        caption=post.get("description"),
        image_paths=image_paths,
        hashtags=post.get("tags", []),
    )


def _fetch_info(url: str, settings: FetchSettings) -> dict:
    ydl_opts = _apply_cookies({
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }, settings)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    duration = info.get("duration", 0)
    cap = settings.max_duration
    if duration > cap:
        raise DurationCapExceeded(duration=duration, cap=cap)
    info.setdefault("tags", [])
    logger.debug("fetched info for %s: duration=%ss", url, duration)
    return info


def _download(url: str, settings: FetchSettings) -> Path:
    ydl_opts = _apply_cookies({
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(settings.temp_dir / "%(id)s.%(ext)s"),
        "format": "mp4/bestvideo+bestaudio/best",
    }, settings)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return Path(ydl.prepare_filename(info))


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


async def fetch(url: str, settings: FetchSettings) -> ReelMetadata:
    """Downloads a reel's media into settings.temp_dir and returns its metadata.
    The caller owns the downloaded files — see ReelMetadata.temp_paths()."""
    canonical, platform = await resolve_canonical_url(url)

    if platform == "tiktok" and is_tiktok_photo_post(canonical):
        _apply_gallery_dl_cookies(settings)
        metadata = await call_with_retry(
            lambda: _fetch_tiktok_photo_post(canonical, settings.temp_dir),
            attempts=DOWNLOAD_RETRY_ATTEMPTS,
            base_delay=DOWNLOAD_RETRY_BASE_DELAY,
            is_retryable=_is_retryable_download_error,
            description=f"fetch TikTok photo post {canonical}",
        )
        logger.info("fetched metadata for %s", canonical)
        return metadata

    if platform == "instagram" and is_instagram_post_path(canonical):
        _apply_gallery_dl_cookies(settings)
        metadata = await call_with_retry(
            lambda: _fetch_instagram_carousel(canonical, settings.temp_dir),
            attempts=DOWNLOAD_RETRY_ATTEMPTS,
            base_delay=DOWNLOAD_RETRY_BASE_DELAY,
            is_retryable=_is_retryable_download_error,
            description=f"fetch Instagram post {canonical}",
        )
        logger.info("fetched metadata for %s", canonical)
        return metadata

    info = await call_with_retry(
        lambda: _fetch_info(canonical, settings),
        attempts=DOWNLOAD_RETRY_ATTEMPTS,
        base_delay=DOWNLOAD_RETRY_BASE_DELAY,
        is_retryable=_is_retryable_download_error,
        description=f"fetch info for {canonical}",
    )
    video_path = await call_with_retry(
        lambda: _download(canonical, settings),
        attempts=DOWNLOAD_RETRY_ATTEMPTS,
        base_delay=DOWNLOAD_RETRY_BASE_DELAY,
        is_retryable=_is_retryable_download_error,
        description=f"download {canonical}",
    )
    metadata = normalize_metadata(info, video_path, platform, canonical)
    logger.info("fetched metadata for %s", canonical)
    return metadata

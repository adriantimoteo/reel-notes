"""Unit tests for reelkit/fetch.py (moved from tests/unit/test_downloader.py).

Settings are passed explicitly via FetchSettings instead of monkeypatching app config.
"""

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reelkit.exceptions import DurationCapExceeded, ReelCaptureError, UnsupportedPlatformError
from reelkit.fetch import (
    FetchSettings,
    _apply_cookies,
    _apply_gallery_dl_cookies,
    _fetch_info,
    _fetch_instagram_carousel,
    _fetch_tiktok_photo_post,
    _is_retryable_download_error,
    _patched_tiktok_post_probe_url,
    fetch,
    normalize_metadata,
)
from reelkit.models import ReelMetadata

SETTINGS = FetchSettings(temp_dir=Path("/tmp/downloads"), max_duration=120)


def test_fetch_settings_defaults() -> None:
    settings = FetchSettings(temp_dir=Path("/tmp/downloads"))
    assert settings.max_duration == 120
    assert settings.cookies_file is None
    assert settings.cookies_from_browser is None


# --- _fetch_info and DurationCapExceeded ---


def test_duration_cap_exceeded_is_subclass_of_reel_capture_error() -> None:
    assert issubclass(DurationCapExceeded, ReelCaptureError)


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_calls_extract_info_with_download_false(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 60, "tags": []}

    result = _fetch_info("https://www.youtube.com/shorts/abc", SETTINGS)

    mock_instance.extract_info.assert_called_once_with("https://www.youtube.com/shorts/abc", download=False)
    assert result == {"duration": 60, "tags": []}


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_raises_duration_cap_exceeded_when_over_limit(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 180, "tags": []}

    with pytest.raises(DurationCapExceeded) as exc_info:
        _fetch_info("https://www.youtube.com/shorts/abc", SETTINGS)

    assert exc_info.value.duration == 180
    assert exc_info.value.cap == 120


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_uses_higher_max_duration_when_given(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 300, "tags": []}

    result = _fetch_info("https://www.youtube.com/shorts/abc", replace(SETTINGS, max_duration=600))

    assert result == {"duration": 300, "tags": []}


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_raises_with_higher_max_duration_when_still_over(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 900, "tags": []}

    with pytest.raises(DurationCapExceeded) as exc_info:
        _fetch_info("https://www.youtube.com/shorts/abc", replace(SETTINGS, max_duration=600))

    assert exc_info.value.duration == 900
    assert exc_info.value.cap == 600


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_returns_info_when_within_limit(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 60, "tags": []}

    result = _fetch_info("https://www.youtube.com/shorts/abc", SETTINGS)

    assert result == {"duration": 60, "tags": []}


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_returns_tags_in_info_dict(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 45, "tags": ["tokyo", "food"]}

    result = _fetch_info("https://www.instagram.com/reel/abc/", SETTINGS)

    assert result["tags"] == ["tokyo", "food"]


@patch("reelkit.fetch.yt_dlp.YoutubeDL")
def test_fetch_info_absent_tags_defaults_to_empty_list(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 45}

    result = _fetch_info("https://www.instagram.com/reel/abc/", SETTINGS)

    assert result["tags"] == []


# --- cookie auth ---


def test_apply_cookies_none_when_unconfigured() -> None:
    opts = _apply_cookies({"quiet": True}, SETTINGS)
    assert "cookiesfrombrowser" not in opts
    assert "cookiefile" not in opts


def test_apply_cookies_from_browser() -> None:
    settings = replace(SETTINGS, cookies_from_browser="chrome", cookies_file=Path("/tmp/cookies.txt"))
    opts = _apply_cookies({}, settings)
    assert opts["cookiesfrombrowser"] == ("chrome",)
    assert "cookiefile" not in opts


def test_apply_cookies_from_file() -> None:
    cookie_path = Path("/tmp/cookies.txt")
    clean_path = Path("/tmp/cookies_clean.txt")
    settings = replace(SETTINGS, cookies_file=cookie_path)
    with patch("reelkit.fetch._sanitize_cookies_file", return_value=clean_path) as mock_san:
        opts = _apply_cookies({}, settings)
    mock_san.assert_called_once_with(cookie_path)
    assert opts["cookiefile"] == str(clean_path)
    assert "cookiesfrombrowser" not in opts


# --- normalize_metadata and fetch ---


def test_normalize_metadata_parses_upload_date() -> None:
    info = {"upload_date": "20260312", "uploader": "TestUser", "title": "Test", "tags": []}
    video_path = Path("/tmp/video.mp4")
    result = normalize_metadata(info, video_path, "instagram", "https://www.instagram.com/reel/abc/")
    assert result.posted_at == datetime(2026, 3, 12)


def test_normalize_metadata_absent_upload_date_gives_none() -> None:
    info = {"uploader": "TestUser", "title": "Test", "tags": []}
    video_path = Path("/tmp/video.mp4")
    result = normalize_metadata(info, video_path, "instagram", "https://www.instagram.com/reel/abc/")
    assert result.posted_at is None


def test_normalize_metadata_maps_hashtags() -> None:
    info = {"tags": ["tokyo", "food"], "uploader": "TestUser", "title": "Test"}
    video_path = Path("/tmp/video.mp4")
    result = normalize_metadata(info, video_path, "tiktok", "https://www.tiktok.com/@user/video/123")
    assert result.hashtags == ["tokyo", "food"]


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_returns_reel_metadata_with_correct_video_path(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    expected_path = Path("/tmp/downloads/abc123.mp4")
    mock_fetch_info.return_value = {
        "duration": 60,
        "uploader": "TestUser",
        "title": "Test Video",
        "tags": [],
        "upload_date": "20260312",
    }
    mock_download.return_value = expected_path

    result = await fetch("https://www.youtube.com/shorts/abc123", SETTINGS)

    assert isinstance(result, ReelMetadata)
    assert result.video_path == expected_path


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_calls_fetch_info_before_download(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    call_order: list[str] = []

    def fake_fetch_info(url: str, settings: FetchSettings) -> dict:
        call_order.append("_fetch_info")
        return {
            "duration": 60,
            "uploader": "TestUser",
            "title": "Test Video",
            "tags": [],
            "upload_date": "20260312",
        }

    def fake_download(url: str, settings: FetchSettings) -> Path:
        call_order.append("_download")
        return Path("/tmp/downloads/abc123.mp4")

    mock_fetch_info.side_effect = fake_fetch_info
    mock_download.side_effect = fake_download

    await fetch("https://www.youtube.com/shorts/abc123", SETTINGS)

    assert call_order == ["_fetch_info", "_download"]


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_passes_settings_through_to_yt_dlp_helpers(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    mock_fetch_info.return_value = {"duration": 60, "tags": []}
    mock_download.return_value = Path("/tmp/downloads/abc123.mp4")

    await fetch("https://www.youtube.com/shorts/abc123", SETTINGS)

    mock_fetch_info.assert_called_once_with("https://www.youtube.com/shorts/abc123", SETTINGS)
    mock_download.assert_called_once_with("https://www.youtube.com/shorts/abc123", SETTINGS)


# --- retry-on-transient-failure ---


def test_is_retryable_returns_false_for_duration_cap_exceeded() -> None:
    assert _is_retryable_download_error(DurationCapExceeded(duration=200, cap=120)) is False


def test_is_retryable_returns_false_for_unsupported_platform() -> None:
    assert _is_retryable_download_error(UnsupportedPlatformError("https://x.com")) is False


def test_is_retryable_returns_true_for_other_errors() -> None:
    assert _is_retryable_download_error(RuntimeError("network blip")) is True


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_retries_fetch_info_on_transient_failure(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    mock_fetch_info.side_effect = [
        RuntimeError("transient"),
        {"duration": 60, "uploader": "TestUser", "title": "Test", "tags": [], "upload_date": "20260312"},
    ]
    mock_download.return_value = Path("/tmp/downloads/abc123.mp4")

    with patch("reelkit.retry.asyncio.sleep", AsyncMock()):
        result = await fetch("https://www.youtube.com/shorts/abc123", SETTINGS)

    assert isinstance(result, ReelMetadata)
    assert mock_fetch_info.call_count == 2


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_does_not_retry_duration_cap_exceeded(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    mock_fetch_info.side_effect = DurationCapExceeded(duration=200, cap=120)

    with pytest.raises(DurationCapExceeded):
        await fetch("https://www.youtube.com/shorts/abc123", SETTINGS)

    assert mock_fetch_info.call_count == 1
    mock_download.assert_not_called()


# --- gallery-dl TiktokPostExtractor.posts() patch (always-probes-/video/ bug workaround) ---


def test_patched_tiktok_posts_probes_photo_url_for_photo_link() -> None:
    fake_self = MagicMock()
    fake_self.groups = ("someuser", "123456")
    fake_self.url = "https://www.tiktok.com/@someuser/photo/123456"
    fake_self.root = "https://www.tiktok.com"

    result = _patched_tiktok_post_probe_url(fake_self)

    assert result == {"https://www.tiktok.com/@someuser/photo/123456": None}


def test_patched_tiktok_posts_probes_video_url_for_video_link() -> None:
    fake_self = MagicMock()
    fake_self.groups = ("someuser", "123456")
    fake_self.url = "https://www.tiktok.com/@someuser/video/123456"
    fake_self.root = "https://www.tiktok.com"

    result = _patched_tiktok_post_probe_url(fake_self)

    assert result == {"https://www.tiktok.com/@someuser/video/123456": None}


def test_patched_tiktok_posts_is_installed_on_the_real_extractor_class() -> None:
    import gallery_dl.extractor.tiktok as gallery_dl_tiktok
    assert gallery_dl_tiktok.TiktokPostExtractor.posts is _patched_tiktok_post_probe_url


# --- fetch() with TikTok short links ---


@patch("reelkit.fetch._apply_gallery_dl_cookies")
@patch("reelkit.fetch._fetch_tiktok_photo_post")
@patch("reelkit.urls._resolve_tiktok_shortlink")
async def test_fetch_resolves_shortlink_before_routing_to_photo_path(
    mock_resolve: MagicMock, mock_fetch_photo: MagicMock, mock_apply_cookies: MagicMock
) -> None:
    mock_resolve.return_value = "https://www.tiktok.com/@user/photo/123456"
    expected = ReelMetadata(
        source_url="x", platform="tiktok", author=None, posted_at=None, title=None,
        caption=None, image_paths=[Path("/tmp/1.jpeg")],
    )
    mock_fetch_photo.return_value = expected

    result = await fetch("https://vt.tiktok.com/ZSqay7spP", SETTINGS)

    assert result is expected
    mock_resolve.assert_called_once_with("https://vt.tiktok.com/ZSqay7spP")
    mock_fetch_photo.assert_called_once_with(
        "https://www.tiktok.com/@user/photo/123456", SETTINGS.temp_dir
    )


@patch("reelkit.fetch._fetch_tiktok_photo_post")
@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
@patch("reelkit.urls._resolve_tiktok_shortlink")
async def test_fetch_shortlink_resolving_to_video_uses_yt_dlp_path(
    mock_resolve: MagicMock,
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
    mock_fetch_photo: MagicMock,
) -> None:
    mock_resolve.return_value = "https://www.tiktok.com/@user/video/123456"
    mock_fetch_info.return_value = {
        "duration": 10, "uploader": "u", "title": "t", "tags": [], "upload_date": "20260101",
    }
    mock_download.return_value = Path("/tmp/downloads/123456.mp4")

    await fetch("https://vt.tiktok.com/ZSomeShortcode", SETTINGS)

    mock_fetch_photo.assert_not_called()
    mock_fetch_info.assert_called_once()


@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
@patch("reelkit.urls._resolve_tiktok_shortlink")
async def test_fetch_falls_back_to_yt_dlp_when_shortlink_resolution_fails(
    mock_resolve: MagicMock,
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
) -> None:
    mock_resolve.side_effect = RuntimeError("network error")
    mock_fetch_info.return_value = {
        "duration": 10, "uploader": "u", "title": "t", "tags": [], "upload_date": "20260101",
    }
    mock_download.return_value = Path("/tmp/downloads/123456.mp4")

    result = await fetch("https://vt.tiktok.com/ZSomeShortcode", SETTINGS)

    assert isinstance(result, ReelMetadata)
    mock_fetch_info.assert_called_once()


# --- gallery-dl cookie wiring ---


def test_apply_gallery_dl_cookies_none_when_unconfigured() -> None:
    with patch("reelkit.fetch.gallery_dl_config.set") as mock_set:
        _apply_gallery_dl_cookies(SETTINGS)
    mock_set.assert_not_called()


def test_apply_gallery_dl_cookies_from_browser() -> None:
    settings = replace(SETTINGS, cookies_from_browser="chrome", cookies_file=Path("/tmp/cookies.txt"))
    with patch("reelkit.fetch.gallery_dl_config.set") as mock_set:
        _apply_gallery_dl_cookies(settings)
    mock_set.assert_called_once_with(("extractor",), "cookies", ("chrome",))


def test_apply_gallery_dl_cookies_from_file() -> None:
    cookie_path = Path("/tmp/cookies.txt")
    clean_path = Path("/tmp/cookies_clean.txt")
    settings = replace(SETTINGS, cookies_file=cookie_path)
    with patch("reelkit.fetch._sanitize_cookies_file", return_value=clean_path) as mock_san, \
         patch("reelkit.fetch.gallery_dl_config.set") as mock_set:
        _apply_gallery_dl_cookies(settings)
    mock_san.assert_called_once_with(cookie_path)
    mock_set.assert_called_once_with(("extractor",), "cookies", str(clean_path))


# --- TikTok photo-post fetch (gallery-dl DataJob path) ---


@patch("reelkit.fetch._download_media_url")
@patch("reelkit.fetch.gallery_dl_job.DataJob")
def test_fetch_tiktok_photo_post_downloads_images_and_audio(
    mock_data_job_class: MagicMock, mock_download: MagicMock, tmp_path: Path
) -> None:
    mock_job = MagicMock()
    mock_job.exception = None
    mock_job.data_post = [{
        "id": "123",
        "desc": "caption text",
        "author": {"uniqueId": "creator"},
        "createTime": "1700000000",
        "textExtra": [{"hashtagName": "tag1"}, {"hashtagName": "tag2"}],
    }]
    mock_job.data_urls = [
        "https://cdn.example.com/img1.jpeg",
        "https://cdn.example.com/img2.jpeg",
        "https://cdn.example.com/audio.mp3",
    ]
    mock_job.data_meta = [
        {"type": "image", "extension": "jpeg"},
        {"type": "image", "extension": "jpeg"},
        {"type": "audio", "extension": "mp3"},
    ]
    mock_data_job_class.return_value = mock_job

    result = _fetch_tiktok_photo_post("https://www.tiktok.com/@user/photo/123", tmp_path)

    assert result.platform == "tiktok"
    assert result.caption == "caption text"
    assert result.author == "creator"
    assert result.hashtags == ["tag1", "tag2"]
    assert result.posted_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)
    assert result.image_paths == [tmp_path / "123_1.jpeg", tmp_path / "123_2.jpeg"]
    assert result.audio_path == tmp_path / "123_audio.mp3"
    assert mock_download.call_count == 3


@patch("reelkit.fetch.gallery_dl_job.DataJob")
def test_fetch_tiktok_photo_post_reraises_job_exception(mock_data_job_class: MagicMock, tmp_path: Path) -> None:
    mock_job = MagicMock()
    mock_job.exception = RuntimeError("challenge solve failed")
    mock_data_job_class.return_value = mock_job

    with pytest.raises(RuntimeError, match="challenge solve failed"):
        _fetch_tiktok_photo_post("https://www.tiktok.com/@user/photo/123", tmp_path)


@patch("reelkit.fetch.gallery_dl_job.DataJob")
def test_fetch_tiktok_photo_post_raises_when_no_post_data(mock_data_job_class: MagicMock, tmp_path: Path) -> None:
    mock_job = MagicMock()
    mock_job.exception = None
    mock_job.data_post = []
    mock_data_job_class.return_value = mock_job

    with pytest.raises(RuntimeError, match="no post data"):
        _fetch_tiktok_photo_post("https://www.tiktok.com/@user/photo/123", tmp_path)


# --- Instagram carousel fetch (gallery-dl DataJob path) ---


@patch("reelkit.fetch._download_media_url")
@patch("reelkit.fetch.gallery_dl_job.DataJob")
def test_fetch_instagram_carousel_downloads_mixed_media(
    mock_data_job_class: MagicMock, mock_download: MagicMock, tmp_path: Path
) -> None:
    mock_job = MagicMock()
    mock_job.exception = None
    posted = datetime(2024, 5, 1, 12, 0, 0)
    mock_job.data_post = [{
        "post_id": "abc123",
        "description": "carousel caption",
        "username": "insta_user",
        "date": posted,
        "tags": ["food", "travel"],
    }]
    mock_job.data_urls = ["https://cdn.example.com/1.jpg", "https://cdn.example.com/2.mp4"]
    mock_job.data_meta = [
        {"extension": "jpg"},
        {"extension": "mp4"},
    ]
    mock_data_job_class.return_value = mock_job

    result = _fetch_instagram_carousel("https://www.instagram.com/p/abc123/", tmp_path)

    assert result.platform == "instagram"
    assert result.caption == "carousel caption"
    assert result.author == "insta_user"
    assert result.posted_at == posted.replace(tzinfo=timezone.utc)
    assert result.hashtags == ["food", "travel"]
    assert result.image_paths == [tmp_path / "abc123_1.jpg", tmp_path / "abc123_2.mp4"]
    assert result.audio_path is None
    assert mock_download.call_count == 2


@patch("reelkit.fetch.gallery_dl_job.DataJob")
def test_fetch_instagram_carousel_raises_when_no_media(mock_data_job_class: MagicMock, tmp_path: Path) -> None:
    mock_job = MagicMock()
    mock_job.exception = None
    mock_job.data_post = [{"post_id": "abc123", "description": "", "username": "u", "date": None, "tags": []}]
    mock_job.data_urls = []
    mock_job.data_meta = []
    mock_data_job_class.return_value = mock_job

    with pytest.raises(RuntimeError, match="no media found"):
        _fetch_instagram_carousel("https://www.instagram.com/p/abc123/", tmp_path)


# --- fetch() routing to the gallery-dl paths ---


@patch("reelkit.fetch._apply_gallery_dl_cookies")
@patch("reelkit.fetch._fetch_tiktok_photo_post")
async def test_fetch_routes_tiktok_photo_post_to_gallery_dl_path(
    mock_fetch_photo: MagicMock, mock_apply_cookies: MagicMock
) -> None:
    expected = ReelMetadata(
        source_url="x", platform="tiktok", author=None, posted_at=None, title=None,
        caption=None, image_paths=[Path("/tmp/1.jpeg")],
    )
    mock_fetch_photo.return_value = expected

    result = await fetch("https://www.tiktok.com/@user/photo/123", SETTINGS)

    assert result is expected
    mock_fetch_photo.assert_called_once()
    mock_apply_cookies.assert_called_once_with(SETTINGS)


@patch("reelkit.fetch._apply_gallery_dl_cookies")
@patch("reelkit.fetch._fetch_instagram_carousel")
async def test_fetch_routes_instagram_post_to_gallery_dl_path(
    mock_fetch_carousel: MagicMock, mock_apply_cookies: MagicMock
) -> None:
    expected = ReelMetadata(
        source_url="x", platform="instagram", author=None, posted_at=None, title=None,
        caption=None, image_paths=[Path("/tmp/1.jpg")],
    )
    mock_fetch_carousel.return_value = expected

    result = await fetch("https://www.instagram.com/p/abc123/", SETTINGS)

    assert result is expected
    mock_fetch_carousel.assert_called_once()
    mock_apply_cookies.assert_called_once_with(SETTINGS)


@patch("reelkit.fetch._fetch_instagram_carousel")
@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_instagram_reel_does_not_use_carousel_path(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
    mock_fetch_carousel: MagicMock,
) -> None:
    mock_fetch_info.return_value = {
        "duration": 10, "uploader": "u", "title": "t", "tags": [], "upload_date": "20260101",
    }
    mock_download.return_value = Path("/tmp/downloads/abc.mp4")

    await fetch("https://www.instagram.com/reel/abc123/", SETTINGS)

    mock_fetch_carousel.assert_not_called()
    mock_fetch_info.assert_called_once()


@patch("reelkit.fetch._fetch_tiktok_photo_post")
@patch("reelkit.fetch._download")
@patch("reelkit.fetch._fetch_info")
async def test_fetch_tiktok_video_does_not_use_photo_path(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
    mock_fetch_photo: MagicMock,
) -> None:
    mock_fetch_info.return_value = {
        "duration": 10, "uploader": "u", "title": "t", "tags": [], "upload_date": "20260101",
    }
    mock_download.return_value = Path("/tmp/downloads/abc.mp4")

    await fetch("https://www.tiktok.com/@user/video/123", SETTINGS)

    mock_fetch_photo.assert_not_called()
    mock_fetch_info.assert_called_once()

"""Unit tests for pipeline/downloader.py — P03T01, P03T02, and P03T03 scope."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

import config
from pipeline.downloader import _fetch_info, canonicalize, detect_platform, fetch, normalize_metadata
from pipeline.exceptions import DurationCapExceeded, ReelCaptureError, UnsupportedPlatformError
from pipeline.models import ReelMetadata


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://www.instagram.com/p/ABC123/", "instagram"),
        ("https://www.instagram.com/tv/ABC123/", "instagram"),
        ("https://www.tiktok.com/@user/video/123456", "tiktok"),
        ("https://vm.tiktok.com/shortcode/", "tiktok"),
        ("https://www.youtube.com/shorts/ABC123", "youtube"),
        ("https://www.youtube.com/watch?v=ABC123", "youtube"),
        ("https://youtu.be/ABC123", "youtube"),
    ],
)
def test_detect_platform(url: str, expected: str) -> None:
    assert detect_platform(url) == expected


def test_detect_platform_unsupported_raises() -> None:
    url = "https://twitter.com/video/123"
    with pytest.raises(UnsupportedPlatformError) as exc_info:
        detect_platform(url)
    assert url in str(exc_info.value)


def test_canonicalize_instagram_strips_tracking() -> None:
    url = "https://www.instagram.com/reel/ABC123/?igsh=xyz"
    result = canonicalize(url, "instagram")
    assert result == "https://www.instagram.com/reel/ABC123/"


def test_canonicalize_tiktok_strips_tracking() -> None:
    url = "https://www.tiktok.com/@user/video/123?_r=1"
    result = canonicalize(url, "tiktok")
    assert result == "https://www.tiktok.com/@user/video/123"


def test_canonicalize_youtube_watch_keeps_v_param() -> None:
    url = "https://www.youtube.com/watch?v=ID&feature=share"
    result = canonicalize(url, "youtube")
    assert result == "https://www.youtube.com/watch?v=ID"


def test_canonicalize_youtube_shorts_strips_params() -> None:
    url = "https://www.youtube.com/shorts/ID?si=xyz"
    result = canonicalize(url, "youtube")
    assert result == "https://www.youtube.com/shorts/ID"


def test_canonicalize_youtu_be_strips_params() -> None:
    url = "https://youtu.be/ABC123?si=xyz"
    result = canonicalize(url, "youtube")
    assert result == "https://youtu.be/ABC123"


def test_unsupported_platform_error_is_subclass_of_reel_capture_error() -> None:
    assert issubclass(UnsupportedPlatformError, ReelCaptureError)


# --- P03T02: _fetch_info and DurationCapExceeded ---


def test_duration_cap_exceeded_is_subclass_of_reel_capture_error() -> None:
    assert issubclass(DurationCapExceeded, ReelCaptureError)


@patch("pipeline.downloader.yt_dlp.YoutubeDL")
def test_fetch_info_calls_extract_info_with_download_false(mock_ydl_class: MagicMock) -> None:
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 60, "tags": []}

    result = _fetch_info("https://www.youtube.com/shorts/abc")

    mock_instance.extract_info.assert_called_once_with("https://www.youtube.com/shorts/abc", download=False)
    assert result == {"duration": 60, "tags": []}


@patch("pipeline.downloader.yt_dlp.YoutubeDL")
def test_fetch_info_raises_duration_cap_exceeded_when_over_limit(mock_ydl_class: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 120)
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 180, "tags": []}

    with pytest.raises(DurationCapExceeded) as exc_info:
        _fetch_info("https://www.youtube.com/shorts/abc")

    assert exc_info.value.duration == 180
    assert exc_info.value.cap == 120


@patch("pipeline.downloader.yt_dlp.YoutubeDL")
def test_fetch_info_returns_info_when_within_limit(mock_ydl_class: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 120)
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 60, "tags": []}

    result = _fetch_info("https://www.youtube.com/shorts/abc")

    assert result == {"duration": 60, "tags": []}


@patch("pipeline.downloader.yt_dlp.YoutubeDL")
def test_fetch_info_returns_tags_in_info_dict(mock_ydl_class: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 120)
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 45, "tags": ["tokyo", "food"]}

    result = _fetch_info("https://www.instagram.com/reel/abc/")

    assert result["tags"] == ["tokyo", "food"]


@patch("pipeline.downloader.yt_dlp.YoutubeDL")
def test_fetch_info_absent_tags_defaults_to_empty_list(mock_ydl_class: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 120)
    mock_instance = MagicMock()
    mock_ydl_class.return_value.__enter__.return_value = mock_instance
    mock_instance.extract_info.return_value = {"duration": 45}

    result = _fetch_info("https://www.instagram.com/reel/abc/")

    assert result["tags"] == []


# --- P03T03: normalize_metadata and fetch ---


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


@patch("pipeline.downloader._download")
@patch("pipeline.downloader._fetch_info")
async def test_fetch_returns_reel_metadata_with_correct_video_path(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "DOWNLOAD_TEMP_DIR", Path("/tmp/downloads"))
    expected_path = Path("/tmp/downloads/abc123.mp4")
    mock_fetch_info.return_value = {
        "duration": 60,
        "uploader": "TestUser",
        "title": "Test Video",
        "tags": [],
        "upload_date": "20260312",
    }
    mock_download.return_value = expected_path

    result = await fetch("https://www.youtube.com/shorts/abc123")

    assert isinstance(result, ReelMetadata)
    assert result.video_path == expected_path


@patch("pipeline.downloader._download")
@patch("pipeline.downloader._fetch_info")
async def test_fetch_calls_fetch_info_before_download(
    mock_fetch_info: MagicMock,
    mock_download: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "DOWNLOAD_TEMP_DIR", Path("/tmp/downloads"))
    call_order: list[str] = []

    def fake_fetch_info(url: str) -> dict:
        call_order.append("_fetch_info")
        return {
            "duration": 60,
            "uploader": "TestUser",
            "title": "Test Video",
            "tags": [],
            "upload_date": "20260312",
        }

    def fake_download(url: str, temp_dir: Path) -> Path:
        call_order.append("_download")
        return Path("/tmp/downloads/abc123.mp4")

    mock_fetch_info.side_effect = fake_fetch_info
    mock_download.side_effect = fake_download

    await fetch("https://www.youtube.com/shorts/abc123")

    assert call_order == ["_fetch_info", "_download"]

"""Unit tests for pipeline/downloader.py — P03T01 scope."""

import pytest

from pipeline.downloader import canonicalize, detect_platform
from pipeline.exceptions import ReelCaptureError, UnsupportedPlatformError


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


def test_unsupported_platform_error_is_subclass_of_reel_capture_error() -> None:
    assert issubclass(UnsupportedPlatformError, ReelCaptureError)

"""Unit tests for reelkit/urls.py (moved from tests/unit/test_downloader.py)."""

from unittest.mock import MagicMock, patch

import pytest

from reelkit.exceptions import ReelCaptureError, UnsupportedCarouselError, UnsupportedPlatformError
from reelkit.urls import (
    _resolve_tiktok_shortlink,
    canonicalize,
    detect_platform,
    detect_reel,
    is_instagram_post_path,
    is_tiktok_photo_post,
    is_tiktok_shortlink,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/reel/ABC123/", "instagram"),
        ("https://www.instagram.com/p/ABC123/", "instagram"),
        ("https://www.instagram.com/tv/ABC123/", "instagram"),
        ("https://www.tiktok.com/@user/video/123456", "tiktok"),
        ("https://vm.tiktok.com/shortcode/", "tiktok"),
        ("https://vt.tiktok.com/shortcode/", "tiktok"),
        ("https://www.tiktok.com/t/shortcode/", "tiktok"),
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


# --- YouTube carousel detection ---


def test_unsupported_carousel_error_is_subclass_of_unsupported_platform_error() -> None:
    assert issubclass(UnsupportedCarouselError, UnsupportedPlatformError)


def test_detect_platform_youtube_post_path_raises_unsupported_carousel() -> None:
    with pytest.raises(UnsupportedCarouselError):
        detect_platform("https://www.youtube.com/post/UgxABC123")


def test_detect_platform_youtube_shorts_still_returns_youtube() -> None:
    assert detect_platform("https://www.youtube.com/shorts/abc123") == "youtube"


# --- TikTok photo-post / Instagram carousel URL detection ---


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.tiktok.com/@user/photo/123456789", True),
        ("https://www.tiktok.com/@user/video/123456789", False),
    ],
)
def test_is_tiktok_photo_post(url: str, expected: bool) -> None:
    assert is_tiktok_photo_post(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/p/ABC123/", True),
        ("https://www.instagram.com/reel/ABC123/", False),
        ("https://www.instagram.com/tv/ABC123/", False),
    ],
)
def test_is_instagram_post_path(url: str, expected: bool) -> None:
    assert is_instagram_post_path(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://vt.tiktok.com/ZSqay7spP", True),
        ("https://vm.tiktok.com/ZMeXXXXXX/", True),
        ("https://www.tiktok.com/@user/video/123", False),
        ("https://www.tiktok.com/@user/photo/123", False),
    ],
)
def test_is_tiktok_shortlink(url: str, expected: bool) -> None:
    assert is_tiktok_shortlink(url) == expected


# --- TikTok short-link resolution (vm./vt.tiktok.com only reveal /photo/ vs /video/ after redirect) ---


@patch("reelkit.urls.urllib.request.urlopen")
def test_resolve_tiktok_shortlink_returns_redirected_url(mock_urlopen: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.url = "https://www.tiktok.com/@user/photo/123456"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    result = _resolve_tiktok_shortlink("https://vt.tiktok.com/ZSqay7spP")

    assert result == "https://www.tiktok.com/@user/photo/123456"


# --- detect_reel (free-text message scanning) ---


@pytest.mark.parametrize("url,expected_platform", [
    ("https://www.instagram.com/reel/abc123/", "instagram"),
    ("https://www.instagram.com/p/abc123/", "instagram"),
    ("https://www.instagram.com/tv/abc123/", "instagram"),
    ("https://www.tiktok.com/@user/video/1234567890", "tiktok"),
    ("https://vm.tiktok.com/ZMshortcode/", "tiktok"),
    ("https://vt.tiktok.com/ZSshortcode/", "tiktok"),
    ("https://www.tiktok.com/t/ZTshortcode/", "tiktok"),
    ("https://www.youtube.com/shorts/abc123", "youtube"),
    ("https://www.youtube.com/watch?v=abc123", "youtube"),
    ("https://youtu.be/abc123", "youtube"),
])
def test_detect_reel_patterns(url: str, expected_platform: str) -> None:
    result = detect_reel(url)
    assert result is not None
    assert result[1] == expected_platform


def test_detect_reel_finds_link_inside_message_text() -> None:
    assert detect_reel("omg go here https://www.instagram.com/reel/abc123/?igsh=x !!") == (
        "instagram.com/reel/abc123", "instagram",
    )


def test_detect_reel_returns_none_without_reel_link() -> None:
    assert detect_reel("see you at 7, https://example.com/menu") is None


def test_detect_reel_does_not_match_full_tiktok_photo_url() -> None:
    """Pins current behaviour: only vm./vt. shortlinks reach the TikTok photo path
    from chat. Change deliberately if full /photo/ URLs should be picked up."""
    assert detect_reel("https://www.tiktok.com/@user/photo/123456") is None

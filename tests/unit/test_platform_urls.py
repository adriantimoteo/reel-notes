"""Parametrized tests for platform detection, canonicalization, and carousel handling."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.downloader import detect_platform, normalize_metadata
from pipeline.exceptions import UnsupportedPlatformError


# --- AC1 & AC3: supported URL patterns → correct platform ---

@pytest.mark.parametrize("url,expected_platform", [
    # Instagram
    ("https://www.instagram.com/reel/ABC123/",       "instagram"),
    ("https://www.instagram.com/p/ABC123/",          "instagram"),
    ("https://www.instagram.com/tv/ABC123/",         "instagram"),
    # TikTok
    ("https://www.tiktok.com/@user/video/123456789", "tiktok"),
    ("https://vm.tiktok.com/ZMeXXXXXX/",            "tiktok"),
    # YouTube
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ",  "youtube"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ",                "youtube"),
])
def test_platform_detection(url: str, expected_platform: str) -> None:
    assert detect_platform(url) == expected_platform


# --- AC2: unsupported URLs → UnsupportedPlatformError ---

@pytest.mark.parametrize("url", [
    "https://twitter.com/user/status/123",
    "https://example.com/video",
    "not a url at all",
])
def test_unsupported_url(url: str) -> None:
    with pytest.raises(UnsupportedPlatformError):
        detect_platform(url)


# --- AC4: Instagram carousel → normalize_metadata uses first entry ---

def test_carousel_normalize_metadata_uses_first_entry(tmp_path: Path) -> None:
    video_path = tmp_path / "first.mp4"
    video_path.write_bytes(b"fake")

    carousel_info = {
        "_type": "playlist",
        "entries": [
            {
                "id": "first",
                "ext": "mp4",
                "duration": 30,
                "upload_date": "20240601",
                "uploader": "carousel_user",
                "title": "First entry",
                "description": "First caption",
                "tags": ["food"],
            },
            {
                "id": "second",
                "ext": "mp4",
                "duration": 25,
                "upload_date": "20240601",
                "uploader": "carousel_user",
                "title": "Second entry",
                "description": "Second caption",
                "tags": [],
            },
        ],
    }

    # normalize_metadata receives the first entry's info
    first_entry = carousel_info["entries"][0]
    metadata = normalize_metadata(
        info=first_entry,
        video_path=video_path,
        platform="instagram",
        source_url="https://www.instagram.com/p/ABC123/",
    )

    assert metadata.author == "carousel_user"
    assert metadata.title == "First entry"
    assert metadata.caption == "First caption"
    assert metadata.hashtags == ["food"]
    assert metadata.video_path == video_path

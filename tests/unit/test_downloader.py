"""Unit tests for pipeline/downloader.py — the config → reelkit.fetch wiring.

Download behaviour itself is tested in packages/reelkit/tests/test_fetch.py.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import config
from pipeline.downloader import fetch, fetch_settings
from reelkit.fetch import FetchSettings
from reelkit.models import ReelMetadata


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "DOWNLOAD_TEMP_DIR", Path("/tmp/downloads"))
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 120)
    monkeypatch.setattr(config, "YTDLP_COOKIES_FILE", Path("/tmp/cookies.txt"))
    monkeypatch.setattr(config, "YTDLP_COOKIES_FROM_BROWSER", "chrome")


def test_fetch_settings_reads_config(configured: None) -> None:
    assert fetch_settings() == FetchSettings(
        temp_dir=Path("/tmp/downloads"),
        max_duration=120,
        cookies_file=Path("/tmp/cookies.txt"),
        cookies_from_browser="chrome",
    )


def test_fetch_settings_max_duration_override(configured: None) -> None:
    assert fetch_settings(max_duration=600).max_duration == 600


def test_fetch_settings_reads_config_at_call_time(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "MAX_VIDEO_DURATION_SECONDS", 90)
    assert fetch_settings().max_duration == 90


def test_fetch_settings_unset_cookies(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "YTDLP_COOKIES_FILE", None)
    monkeypatch.setattr(config, "YTDLP_COOKIES_FROM_BROWSER", None)
    settings = fetch_settings()
    assert settings.cookies_file is None
    assert settings.cookies_from_browser is None


async def test_fetch_delegates_to_reelkit_with_config_settings(configured: None) -> None:
    expected = ReelMetadata(
        source_url="x", platform="youtube", author=None, posted_at=None, title=None, caption=None,
    )
    with patch("pipeline.downloader._reelkit_fetch.fetch", AsyncMock(return_value=expected)) as mock_fetch:
        result = await fetch("https://www.youtube.com/shorts/abc123")

    assert result is expected
    mock_fetch.assert_awaited_once_with("https://www.youtube.com/shorts/abc123", fetch_settings())


async def test_fetch_passes_force_cap_through(configured: None) -> None:
    with patch("pipeline.downloader._reelkit_fetch.fetch", AsyncMock()) as mock_fetch:
        await fetch("https://www.youtube.com/shorts/abc123", max_duration=600)

    settings = mock_fetch.await_args.args[1]
    assert settings.max_duration == 600

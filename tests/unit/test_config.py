"""Tests for config.py — all env vars are monkeypatched; real .env is never read."""

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

import config

ALL_VARS = {
    "TELEGRAM_BOT_TOKEN": "test-bot-token",
    "TELEGRAM_ALLOWED_USER_ID": "42",
    "GEMINI_API_KEY": "test-gemini-key",
    "VAULT_PATH": "/tmp/vault",
    "VAULT_NOTES_SUBDIR": "notes",
    "DB_PATH": "/tmp/db.sqlite",
    "DOWNLOAD_TEMP_DIR": "/tmp/downloads",
    "MAX_VIDEO_DURATION_SECONDS": "180",
}

REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USER_ID",
    "GEMINI_API_KEY",
    "VAULT_PATH",
    "VAULT_NOTES_SUBDIR",
    "DB_PATH",
    "DOWNLOAD_TEMP_DIR",
]


def reload_config(monkeypatch: pytest.MonkeyPatch, env: dict[str, str]) -> object:
    for var in list(ALL_VARS.keys()):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    with patch("dotenv.load_dotenv"):
        return importlib.reload(config)


def test_all_vars_present_correct_types(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = reload_config(monkeypatch, ALL_VARS)

    assert isinstance(cfg.TELEGRAM_BOT_TOKEN, str)
    assert cfg.TELEGRAM_BOT_TOKEN == "test-bot-token"

    assert isinstance(cfg.TELEGRAM_ALLOWED_USER_ID, int)
    assert cfg.TELEGRAM_ALLOWED_USER_ID == 42

    assert isinstance(cfg.GEMINI_API_KEY, str)
    assert cfg.GEMINI_API_KEY == "test-gemini-key"

    assert isinstance(cfg.VAULT_PATH, Path)
    assert cfg.VAULT_PATH == Path("/tmp/vault")

    assert isinstance(cfg.VAULT_NOTES_SUBDIR, str)
    assert cfg.VAULT_NOTES_SUBDIR == "notes"

    assert isinstance(cfg.DB_PATH, Path)
    assert cfg.DB_PATH == Path("/tmp/db.sqlite")

    assert isinstance(cfg.DOWNLOAD_TEMP_DIR, Path)
    assert cfg.DOWNLOAD_TEMP_DIR == Path("/tmp/downloads")

    assert isinstance(cfg.MAX_VIDEO_DURATION_SECONDS, int)
    assert cfg.MAX_VIDEO_DURATION_SECONDS == 180


def test_max_video_duration_defaults_to_120(monkeypatch: pytest.MonkeyPatch) -> None:
    env = {k: v for k, v in ALL_VARS.items() if k != "MAX_VIDEO_DURATION_SECONDS"}
    cfg = reload_config(monkeypatch, env)
    assert cfg.MAX_VIDEO_DURATION_SECONDS == 120


@pytest.mark.parametrize("missing_var", REQUIRED_VARS)
def test_missing_required_var_raises_config_error(
    monkeypatch: pytest.MonkeyPatch, missing_var: str
) -> None:
    env = {k: v for k, v in ALL_VARS.items() if k != missing_var}

    for var in list(ALL_VARS.keys()):
        monkeypatch.delenv(var, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    with patch("dotenv.load_dotenv"):
        try:
            importlib.reload(config)
            pytest.fail(f"Expected ConfigError for missing {missing_var}")
        except Exception as exc:
            assert type(exc).__name__ == "ConfigError", (
                f"Expected ConfigError, got {type(exc).__name__}: {exc}"
            )
            assert missing_var in str(exc), (
                f"Expected '{missing_var}' in error message, got: {exc}"
            )

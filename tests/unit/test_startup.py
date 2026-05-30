"""Tests for validate_config and log_startup_config."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from main import validate_config, log_startup_config


def _mock_config(tmp_path: Path, **overrides):
    vault = tmp_path / "vault"
    vault.mkdir()
    db_parent = tmp_path / "db"
    db_parent.mkdir()
    temp_parent = tmp_path / "tmp_parent"
    temp_parent.mkdir()

    defaults = dict(
        VAULT_PATH=vault,
        DB_PATH=db_parent / "reels.db",
        DOWNLOAD_TEMP_DIR=temp_parent / "tmp",
        MAX_VIDEO_DURATION_SECONDS=120,
        TELEGRAM_BOT_TOKEN="ABCDEF1234567890abcd1234",
        GEMINI_API_KEY="AIzaSyABCDEFGHIJ1234",
        TELEGRAM_ALLOWED_USER_ID=123456789,
    )
    defaults.update(overrides)
    return defaults


# --- AC3: all valid → returns without raising ---

def test_validate_config_passes_with_valid_paths(tmp_path: Path) -> None:
    cfg = _mock_config(tmp_path)
    with patch.multiple("main.config", **cfg):
        validate_config()  # should not raise


# --- AC1: non-existent VAULT_PATH → SystemExit(1) with "VAULT_PATH" in output ---

def test_validate_config_raises_for_missing_vault_path(tmp_path: Path, capsys) -> None:
    cfg = _mock_config(tmp_path, VAULT_PATH=tmp_path / "missing_vault")
    with patch.multiple("main.config", **cfg):
        with pytest.raises(SystemExit) as exc_info:
            validate_config()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "VAULT_PATH" in captured.out


# --- VAULT_PATH exists but is a file, not a dir ---

def test_validate_config_raises_when_vault_path_is_file(tmp_path: Path, capsys) -> None:
    vault_file = tmp_path / "vault.txt"
    vault_file.write_text("not a dir")
    cfg = _mock_config(tmp_path, VAULT_PATH=vault_file)
    with patch.multiple("main.config", **cfg):
        with pytest.raises(SystemExit) as exc_info:
            validate_config()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "VAULT_PATH" in captured.out


# --- AC2: non-existent DB_PATH parent → SystemExit(1) with "DB_PATH" in output ---

def test_validate_config_raises_for_missing_db_parent(tmp_path: Path, capsys) -> None:
    cfg = _mock_config(tmp_path, DB_PATH=tmp_path / "no_dir" / "reels.db")
    with patch.multiple("main.config", **cfg):
        with pytest.raises(SystemExit) as exc_info:
            validate_config()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "DB_PATH" in captured.out


# --- AC4: multiple invalid paths → all errors printed before SystemExit ---

def test_validate_config_reports_all_errors(tmp_path: Path, capsys) -> None:
    cfg = _mock_config(
        tmp_path,
        VAULT_PATH=tmp_path / "no_vault",
        DB_PATH=tmp_path / "no_db_dir" / "reels.db",
    )
    with patch.multiple("main.config", **cfg):
        with pytest.raises(SystemExit):
            validate_config()
    captured = capsys.readouterr()
    assert "VAULT_PATH" in captured.out
    assert "DB_PATH" in captured.out


# --- AC5: secrets are redacted in startup config log ---

def test_log_startup_config_redacts_secrets(tmp_path: Path, capsys) -> None:
    token = "ABCDEF1234567890abcd1234"
    api_key = "AIzaSyABCDEFGHIJ1234"
    cfg = _mock_config(tmp_path, TELEGRAM_BOT_TOKEN=token, GEMINI_API_KEY=api_key)
    with patch.multiple("main.config", **cfg):
        log_startup_config()
    captured = capsys.readouterr()
    assert token not in captured.out
    assert api_key not in captured.out
    assert "****" in captured.out
    # Last 4 chars should appear
    assert token[-4:] in captured.out
    assert api_key[-4:] in captured.out

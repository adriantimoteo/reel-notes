"""Application configuration."""

import os
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(Exception):
    pass


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _load() -> None:
    load_dotenv()

    global TELEGRAM_BOT_TOKEN
    global TELEGRAM_ALLOWED_USER_ID
    global GEMINI_API_KEY
    global VAULT_PATH
    global VAULT_NOTES_SUBDIR
    global DB_PATH
    global DOWNLOAD_TEMP_DIR
    global MAX_VIDEO_DURATION_SECONDS
    global LOG_LEVEL

    TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
    TELEGRAM_ALLOWED_USER_ID = int(_require("TELEGRAM_ALLOWED_USER_ID"))
    GEMINI_API_KEY = _require("GEMINI_API_KEY")
    VAULT_PATH = Path(_require("VAULT_PATH"))
    VAULT_NOTES_SUBDIR = _require("VAULT_NOTES_SUBDIR")
    DB_PATH = Path(_require("DB_PATH"))
    DOWNLOAD_TEMP_DIR = Path(_require("DOWNLOAD_TEMP_DIR"))
    MAX_VIDEO_DURATION_SECONDS = int(os.getenv("MAX_VIDEO_DURATION_SECONDS", "120"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


TELEGRAM_BOT_TOKEN: str
TELEGRAM_ALLOWED_USER_ID: int
GEMINI_API_KEY: str
VAULT_PATH: Path
VAULT_NOTES_SUBDIR: str
DB_PATH: Path
DOWNLOAD_TEMP_DIR: Path
MAX_VIDEO_DURATION_SECONDS: int
LOG_LEVEL: str

_load()

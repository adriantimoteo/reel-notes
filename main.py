"""Entry point for the reel-capture-bot."""

import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher

import config
from bot.handlers import register_handlers
from output.writers import LocalFolderWriter
from storage.db import get_connection, init_db

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def validate_config() -> None:
    errors = []

    if not config.VAULT_PATH.exists():
        errors.append(f"VAULT_PATH does not exist: {config.VAULT_PATH}")
    elif not config.VAULT_PATH.is_dir():
        errors.append(f"VAULT_PATH is not a directory: {config.VAULT_PATH}")

    db_parent = config.DB_PATH.parent
    if not db_parent.exists():
        errors.append(f"DB_PATH parent directory does not exist: {db_parent}")

    temp_parent = config.DOWNLOAD_TEMP_DIR.parent
    if not temp_parent.exists():
        errors.append(f"DOWNLOAD_TEMP_DIR parent does not exist: {temp_parent}")

    if errors:
        for err in errors:
            logger.error("%s", err)
        raise SystemExit(1)


def _redact(secret: str) -> str:
    return f"****...{secret[-4:]}" if len(secret) >= 4 else "****"


def log_startup_config() -> None:
    logger.info("reel-capture-bot")
    logger.info("vault:    %s", config.VAULT_PATH)
    logger.info("db:       %s", config.DB_PATH)
    logger.info("temp dir: %s", config.DOWNLOAD_TEMP_DIR)
    logger.info("max dur:  %ss", config.MAX_VIDEO_DURATION_SECONDS)
    logger.info("bot token: %s", _redact(config.TELEGRAM_BOT_TOKEN))
    logger.info("gemini key: %s", _redact(config.GEMINI_API_KEY))
    logger.info("allowed user: %s", config.TELEGRAM_ALLOWED_USER_ID)


def cleanup_temp_dir(temp_dir: Path) -> int:
    """Delete stale video files. Returns count of files removed."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for ext in ("*.mp4", "*.webm", "*.mkv", "*.m4v"):
        for f in temp_dir.glob(ext):
            f.unlink(missing_ok=True)
            removed += 1
    return removed


async def main() -> None:
    validate_config()
    log_startup_config()
    n = cleanup_temp_dir(config.DOWNLOAD_TEMP_DIR)
    logger.info("cleaned up %d stale temp files", n)

    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    vault_writer = LocalFolderWriter(config.VAULT_PATH, config.VAULT_NOTES_SUBDIR)
    register_handlers(dp, bot, conn, vault_writer)
    try:
        logger.info("bot started")
        await dp.start_polling(bot)
    finally:
        conn.close()
        await bot.session.close()
        logger.info("shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

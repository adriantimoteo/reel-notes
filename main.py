"""Entry point for the reel-capture-bot."""

import asyncio
import logging

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


async def main() -> None:
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

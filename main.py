"""Entry point for the reel-capture-bot."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

import config
from bot.handlers import register_handlers

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(levelname)-5s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    register_handlers(dp)
    try:
        logger.info("bot started")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())

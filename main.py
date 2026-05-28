"""Entry point for the reel-capture-bot."""

import asyncio

from aiogram import Bot, Dispatcher

import config
from bot.handlers import register_handlers


async def main() -> None:
    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    register_handlers(dp)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

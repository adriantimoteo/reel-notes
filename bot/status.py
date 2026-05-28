"""Bot status reporting utilities."""

from aiogram import Bot


class StatusMessage:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot
        self._chat_id: int | None = None
        self._message_id: int | None = None

    async def send(self, chat_id: int, initial_text: str) -> None:
        sent = await self._bot.send_message(chat_id, initial_text)
        self._chat_id = chat_id
        self._message_id = sent.message_id

    async def update(self, text: str) -> None:
        await self._bot.edit_message_text(
            text,
            chat_id=self._chat_id,
            message_id=self._message_id,
        )

"""The progress-reporting interface pipeline code depends on, so it doesn't need
to know whether updates go to a Telegram message, a log, or nowhere."""

from typing import Protocol


class StatusReporter(Protocol):
    async def update(self, text: str) -> None: ...

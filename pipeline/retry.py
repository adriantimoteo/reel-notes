"""Retry helper for transient failures in external network calls."""

import asyncio
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def call_with_retry(
    func: Callable[[], T],
    *,
    attempts: int,
    base_delay: float,
    is_retryable: Callable[[Exception], bool],
    description: str,
) -> T:
    """Runs blocking `func` in a thread, retrying transient failures with exponential backoff.

    `is_retryable` decides whether a given exception is worth retrying; a
    non-retryable exception, or the last attempt, is always re-raised as-is.
    """
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.to_thread(func)
        except Exception as e:
            if attempt == attempts or not is_retryable(e):
                raise
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.0fs",
                description, attempt, attempts, e, delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover

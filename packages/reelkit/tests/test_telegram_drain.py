"""Tests for reelkit.telegram.drain.drain_pending."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramNetworkError

from reelkit.telegram.drain import drain_pending


def _make_update(update_id: int) -> MagicMock:
    update = MagicMock()
    update.update_id = update_id
    return update


@pytest.mark.asyncio
async def test_drain_pending_processes_all_batches_in_order() -> None:
    batch1 = [_make_update(1), _make_update(2)]
    batch2 = [_make_update(3)]
    bot = AsyncMock(side_effect=[batch1, batch2, []])
    dp = MagicMock()
    dp.feed_update = AsyncMock()

    processed = await drain_pending(bot, dp)

    assert processed == 3
    assert dp.feed_update.await_count == 3
    fed_ids = [call.args[1].update_id for call in dp.feed_update.await_args_list]
    assert fed_ids == [1, 2, 3]

    offsets = [call.args[0].offset for call in bot.await_args_list]
    assert offsets == [None, 3, 4]


@pytest.mark.asyncio
async def test_drain_pending_returns_zero_when_nothing_queued() -> None:
    bot = AsyncMock(return_value=[])
    dp = MagicMock()
    dp.feed_update = AsyncMock()

    processed = await drain_pending(bot, dp)

    assert processed == 0
    dp.feed_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_pending_returns_none_when_offline() -> None:
    bot = AsyncMock(side_effect=TelegramNetworkError(method=MagicMock(), message="no route"))
    dp = MagicMock()
    dp.feed_update = AsyncMock()

    processed = await drain_pending(bot, dp)

    assert processed is None
    dp.feed_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_drain_pending_propagates_unexpected_errors() -> None:
    bot = AsyncMock(side_effect=[[_make_update(1)]])
    dp = MagicMock()
    dp.feed_update = AsyncMock(side_effect=RuntimeError("bug"))

    with pytest.raises(RuntimeError):
        await drain_pending(bot, dp)

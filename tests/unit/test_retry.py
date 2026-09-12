"""Unit tests for pipeline/retry.py."""

from unittest.mock import AsyncMock, patch

import pytest

from pipeline.retry import call_with_retry


async def test_returns_result_on_first_success() -> None:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        return "ok"

    result = await call_with_retry(
        func, attempts=3, base_delay=0.01, is_retryable=lambda e: True, description="test"
    )

    assert result == "ok"
    assert len(calls) == 1


async def test_retries_retryable_failure_then_succeeds() -> None:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    with patch("pipeline.retry.asyncio.sleep", AsyncMock()) as mock_sleep:
        result = await call_with_retry(
            func, attempts=3, base_delay=2.0, is_retryable=lambda e: True, description="test"
        )

    assert result == "ok"
    assert len(calls) == 3
    assert mock_sleep.call_args_list == [((2.0,),), ((4.0,),)]


async def test_does_not_retry_non_retryable_failure() -> None:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        raise ValueError("permanent")

    with patch("pipeline.retry.asyncio.sleep", AsyncMock()) as mock_sleep:
        with pytest.raises(ValueError):
            await call_with_retry(
                func, attempts=3, base_delay=1.0, is_retryable=lambda e: False, description="test"
            )

    assert len(calls) == 1
    mock_sleep.assert_not_called()


async def test_raises_after_exhausting_attempts() -> None:
    calls: list[int] = []

    def func() -> str:
        calls.append(1)
        raise RuntimeError("still failing")

    with patch("pipeline.retry.asyncio.sleep", AsyncMock()):
        with pytest.raises(RuntimeError, match="still failing"):
            await call_with_retry(
                func, attempts=3, base_delay=0.01, is_retryable=lambda e: True, description="test"
            )

    assert len(calls) == 3

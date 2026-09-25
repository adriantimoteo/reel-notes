"""Tests for failure classification and the next-run retry sweep."""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from google.genai import errors as genai_errors

from pipeline import orchestrator, retry_sweep
from pipeline.exceptions import ExtractionError
from pipeline.models import ExtractionResult, ReelMetadata
from storage import repository
from storage.db import get_connection, init_db

URL = "https://www.tiktok.com/@someone/video/123"
EMPTY = ExtractionResult(transcription="", ocr_text="", summary="", title="")


@pytest.fixture
def conn() -> sqlite3.Connection:
    db_path = Path(f"file:{uuid.uuid4().hex}?mode=memory&cache=shared")
    c = get_connection(db_path)
    init_db(db_path)
    yield c
    c.close()


def _metadata(url: str = URL) -> ReelMetadata:
    return ReelMetadata(
        source_url=url,
        platform="tiktok",
        author="a",
        posted_at=datetime(2024, 1, 1),
        title="t",
        caption=None,
        video_path=Path("/tmp/v.mp4"),
    )


def _server_error() -> genai_errors.ServerError:
    return genai_errors.ServerError(503, {"error": {"message": "overloaded", "status": "UNAVAILABLE"}})


def _client_error(code: int) -> genai_errors.ClientError:
    return genai_errors.ClientError(code, {"error": {"message": "nope", "status": "X"}})


# --- transient classification ---

@pytest.mark.parametrize(
    "cause",
    [_server_error(), _client_error(429), ConnectionAbortedError(10053, "aborted"), TimeoutError(), httpx.ConnectError("x")],
)
def test_transient_extraction_errors_are_retryable(cause: Exception) -> None:
    assert orchestrator._is_transient(ExtractionError(cause=cause))


@pytest.mark.parametrize("cause", [_client_error(404), _client_error(400), ValueError("bad json")])
def test_permanent_extraction_errors_are_not_retryable(cause: Exception) -> None:
    assert not orchestrator._is_transient(ExtractionError(cause=cause))


def test_non_extraction_errors_are_not_retryable() -> None:
    assert not orchestrator._is_transient(RuntimeError("boom"))


# --- run(): failure bookkeeping ---

async def test_run_marks_row_retryable_when_extraction_hits_503(conn, tmp_path) -> None:
    updates: list[str] = []
    status = MagicMock()
    status.update = AsyncMock(side_effect=updates.append)

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=_metadata())), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=_server_error())):
        ok = await orchestrator.run(URL, status, conn, MagicMock())

    assert ok is False
    assert URL in updates[-1], "failure message must include the link"
    row = await repository.find_by_url(conn, URL)
    assert row["vault_note_path"] is None
    assert row["retryable"] == 1
    assert "503" in row["last_error"]


async def test_run_marks_row_not_retryable_for_permanent_failure(conn) -> None:
    status = MagicMock()
    status.update = AsyncMock()

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=_metadata())), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=ValueError("bad json"))):
        await orchestrator.run(URL, status, conn, MagicMock())

    row = await repository.find_by_url(conn, URL)
    assert row["retryable"] == 0


async def test_run_carries_prior_attempts_onto_recreated_row(conn) -> None:
    await repository.save_reel(conn, _metadata(), EMPTY)
    status = MagicMock()
    status.update = AsyncMock()

    with patch("pipeline.orchestrator.downloader.fetch", AsyncMock(return_value=_metadata())), \
         patch("pipeline.orchestrator.extractor.extract", AsyncMock(side_effect=_server_error())):
        await orchestrator.run(URL, status, conn, MagicMock(), prior_attempts=2)

    row = await repository.find_by_url(conn, URL)
    assert row["attempts"] == 2


# --- repository.find_retryable ---

async def test_find_retryable_filters_by_note_attempts_and_flag(conn) -> None:
    pending = await repository.save_reel(conn, _metadata("https://x/pending"), EMPTY)
    legacy_null_flag = await repository.save_reel(conn, _metadata("https://x/legacy"), EMPTY)
    done = await repository.save_reel(conn, _metadata("https://x/done"), EMPTY)
    exhausted = await repository.save_reel(conn, _metadata("https://x/exhausted"), EMPTY, attempts=3)
    permanent = await repository.save_reel(conn, _metadata("https://x/permanent"), EMPTY)

    await repository.mark_failed(conn, pending, "503", retryable=True)
    await repository.update_vault_path(conn, done, "n.md")
    await repository.mark_failed(conn, permanent, "bad", retryable=False)

    ids = [r["id"] for r in await repository.find_retryable(conn, 3)]
    assert ids == [pending, legacy_null_flag]
    assert exhausted not in ids and done not in ids and permanent not in ids


# --- retry_sweep ---

def _bot() -> MagicMock:
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


async def test_sweep_notifies_on_success(conn) -> None:
    reel_id = await repository.save_reel(conn, _metadata(), EMPTY)
    bot = _bot()

    async def fake_run(url, status, conn_, writer, prior_attempts=0, **kw):
        await status.update("saved · note.md")
        return True

    with patch("pipeline.retry_sweep.orchestrator.run", side_effect=fake_run) as run:
        await retry_sweep.retry_pending(bot, conn, MagicMock(), await retry_sweep.find_pending(conn))

    assert run.call_args.kwargs["prior_attempts"] == 1
    sent = bot.send_message.call_args.args[1]
    assert "retry succeeded" in sent and "note.md" in sent
    assert reel_id  # row existed before the retry


async def test_sweep_stays_quiet_when_it_will_retry_again(conn) -> None:
    reel_id = await repository.save_reel(conn, _metadata(), EMPTY)
    await repository.mark_failed(conn, reel_id, "503", retryable=True)
    bot = _bot()

    async def fake_run(url, status, conn_, writer, prior_attempts=0, **kw):
        await status.update(f"extraction failed · 503\n{url}")
        return False

    with patch("pipeline.retry_sweep.orchestrator.run", side_effect=fake_run):
        await retry_sweep.retry_pending(bot, conn, MagicMock(), await retry_sweep.find_pending(conn))

    bot.send_message.assert_not_called()
    assert (await repository.find_by_url(conn, URL))["attempts"] == 1


async def test_sweep_sends_link_when_giving_up_after_last_attempt(conn) -> None:
    reel_id = await repository.save_reel(
        conn, _metadata(), EMPTY, attempts=retry_sweep.MAX_RETRY_ATTEMPTS - 1
    )
    await repository.mark_failed(conn, reel_id, "503", retryable=True)
    bot = _bot()

    async def fake_run(url, status, conn_, writer, prior_attempts=0, **kw):
        await status.update(f"extraction failed · 503\n{url}")
        return False

    with patch("pipeline.retry_sweep.orchestrator.run", side_effect=fake_run):
        await retry_sweep.retry_pending(bot, conn, MagicMock(), await retry_sweep.find_pending(conn))

    sent = bot.send_message.call_args.args[1]
    assert URL in sent
    assert "not retrying automatically" in sent


async def test_sweep_skips_reels_handled_earlier_in_the_same_run(conn) -> None:
    reel_id = await repository.save_reel(conn, _metadata(), EMPTY)
    pending = await retry_sweep.find_pending(conn)
    # the owner resent the link during the drain and it succeeded
    await repository.update_vault_path(conn, reel_id, "note.md")
    bot = _bot()

    with patch("pipeline.retry_sweep.orchestrator.run", AsyncMock()) as run:
        await retry_sweep.retry_pending(bot, conn, MagicMock(), pending)

    run.assert_not_called()
    bot.send_message.assert_not_called()


async def test_sweep_stops_when_time_budget_is_used_up(conn) -> None:
    first = await repository.save_reel(conn, _metadata("https://x/first"), EMPTY)
    second = await repository.save_reel(conn, _metadata("https://x/second"), EMPTY)
    pending = await retry_sweep.find_pending(conn)
    bot = _bot()

    async def fake_run(url, status, conn_, writer, prior_attempts=0, **kw):
        await status.update("saved · note.md")
        return True

    # start=0, first check=0 (within budget), second check=100 (over budget)
    with patch("pipeline.retry_sweep.time") as fake_time,          patch("pipeline.retry_sweep.orchestrator.run", side_effect=fake_run) as run:
        fake_time.monotonic.side_effect = [0, 0, 100]
        await retry_sweep.retry_pending(bot, conn, MagicMock(), pending, time_budget=50)

    assert [c.args[0] for c in run.call_args_list] == ["https://x/first"]
    untouched = await repository.find_by_url(conn, "https://x/second")
    assert untouched["id"] == second and untouched["attempts"] == 0, "unreached reel must not lose an attempt"
    assert first

"""Budgeted AeroAPI board client, with a real Redis budget and a mock transport."""

import httpx
import pytest

from backend.ingest.aeroapi_budget import AeroApiBudget, BudgetDenial
from backend.ingest.aeroapi_client import (
    AUTH_FAILURE_PAUSE_SECONDS,
    RATE_LIMITED_PAUSE_SECONDS,
    AeroApiClient,
    BoardEndpoint,
    BoardPage,
    FetchFailure,
)
from backend.utils.redis_async import RedisClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

ARRIVALS = BoardEndpoint.SCHEDULED_ARRIVALS


class FakeAeroApi:
    """Records requests and answers with a canned status and body."""

    def __init__(self, status: int = 200, body: dict | None = None) -> None:
        self.status = status
        self.body = body if body is not None else {"scheduled_arrivals": [], "num_pages": 1}
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(self.status, json=self.body)


def _client(redis: RedisClient, clock, api: FakeAeroApi, daily_cap: int = 25) -> AeroApiClient:
    budget = AeroApiBudget(redis, daily_cap=daily_cap, per_minute_cap=8, clock=clock)
    return AeroApiClient(
        "test-key", budget, "KBOS", transport=httpx.MockTransport(api.handler), clock=clock
    )


async def test_requests_the_airport_board_with_window_and_page_limit(
    real_redis_client: RedisClient, clock
) -> None:
    api = FakeAeroApi()
    client = _client(real_redis_client, clock, api)

    await client.fetch_board(ARRIVALS, start=clock() - 900, end=clock() + 5400, max_pages=2)

    [request] = api.requests
    assert request.url.path == "/aeroapi/airports/KBOS/flights/scheduled_arrivals"
    assert dict(request.url.params) == {
        "start": "2026-10-16T11:45:30Z",
        "end": "2026-10-16T13:30:30Z",
        "max_pages": "2",
    }
    assert request.headers["x-apikey"] == "test-key"


async def test_returns_rows_and_detects_more_pages(real_redis_client: RedisClient, clock) -> None:
    api = FakeAeroApi(
        body={
            "scheduled_arrivals": [{"ident": "JBU1"}],
            "links": {"next": "/airports/KBOS/flights/scheduled_arrivals?cursor=abc"},
            "num_pages": 1,
        }
    )
    client = _client(real_redis_client, clock, api)

    page = await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=1)

    assert page == BoardPage(rows=[{"ident": "JBU1"}], truncated=True)


async def test_no_request_once_the_daily_cap_is_spent(
    real_redis_client: RedisClient, clock
) -> None:
    api = FakeAeroApi()
    client = _client(real_redis_client, clock, api, daily_cap=2)
    await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=2)
    clock.advance(120)

    outcome = await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=1)

    assert outcome == BudgetDenial.DAILY_CAP
    assert len(api.requests) == 1


async def test_rate_limited_response_pauses_requests(real_redis_client: RedisClient, clock) -> None:
    api = FakeAeroApi(status=429, body={})
    client = _client(real_redis_client, clock, api)
    await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=1)

    clock.advance(RATE_LIMITED_PAUSE_SECONDS - 1)
    assert await client.fetch_board(ARRIVALS, clock(), clock(), 1) == FetchFailure.PAUSED
    clock.advance(2)
    await client.fetch_board(ARRIVALS, clock(), clock(), 1)

    assert len(api.requests) == 2


async def test_rejected_key_pauses_for_an_hour_and_logs_error(
    real_redis_client: RedisClient, clock, caplog: pytest.LogCaptureFixture
) -> None:
    api = FakeAeroApi(status=401, body={})
    client = _client(real_redis_client, clock, api)
    await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=1)

    clock.advance(AUTH_FAILURE_PAUSE_SECONDS - 1)

    assert await client.fetch_board(ARRIVALS, clock(), clock(), 1) == FetchFailure.PAUSED
    assert len(api.requests) == 1
    assert any(
        r.levelname == "ERROR" and "FLIGHTAWARE_API_KEY" in r.message for r in caplog.records
    )


async def test_failed_request_still_counts_against_the_budget(
    real_redis_client: RedisClient, clock
) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    budget = AeroApiBudget(real_redis_client, daily_cap=25, per_minute_cap=8, clock=clock)
    client = AeroApiClient("k", budget, "KBOS", transport=httpx.MockTransport(broken), clock=clock)

    outcome = await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=2)

    assert outcome == FetchFailure.TRANSPORT_ERROR
    assert await real_redis_client.get("aeroapi:result_sets:2026-10-16") == "2"


def _usage_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [
        r.message
        for r in caplog.records
        if r.name == "backend.ingest.aeroapi_client" and r.levelname == "INFO"
    ]


async def test_logs_one_usage_line_per_request_without_the_key(
    real_redis_client: RedisClient, clock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO", logger="backend.ingest.aeroapi_client")
    client = _client(real_redis_client, clock, FakeAeroApi())

    await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=2)

    [line] = _usage_lines(caplog)
    assert "scheduled_arrivals status=200" in line
    assert "today 2/25 result sets ($0.010)" in line
    assert "test-key" not in caplog.text


async def test_request_that_never_got_an_answer_still_logs_its_usage(
    real_redis_client: RedisClient, clock, caplog: pytest.LogCaptureFixture
) -> None:
    """A timed-out request may have been billed, so it shows in the usage log too."""

    def timed_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    caplog.set_level("INFO", logger="backend.ingest.aeroapi_client")
    budget = AeroApiBudget(real_redis_client, daily_cap=25, per_minute_cap=8, clock=clock)
    client = AeroApiClient(
        "test-key", budget, "KBOS", transport=httpx.MockTransport(timed_out), clock=clock
    )

    await client.fetch_board(ARRIVALS, clock(), clock() + 3600, max_pages=2)

    [line] = _usage_lines(caplog)
    assert "scheduled_arrivals status=-" in line
    assert "today 2/25 result sets ($0.010)" in line

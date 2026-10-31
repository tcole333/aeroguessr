"""AeroAPI spending fails closed when Redis is unreachable.

These need no Redis server (nothing listens on the URL they use), so they run
with the unit tests.
"""

import httpx
import pytest

from backend.ingest.aeroapi_budget import AeroApiBudget, BudgetDenial
from backend.ingest.aeroapi_client import AeroApiClient, BoardEndpoint
from backend.ingest.airport_board import AirportBoard
from backend.ingest.board_refresher import BoardRefresher
from backend.ingest.enrichment_config import EnrichmentConfig
from backend.ingest.enrichment_gate import EnrichmentGate, GateReason
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio

OPEN_CONFIG = EnrichmentConfig(api_key="test-key")


@pytest.fixture
def unreachable_redis(monkeypatch: pytest.MonkeyPatch) -> RedisClient:
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/9")  # nothing listens here
    return RedisClient()


@pytest.fixture
def aeroapi_requests() -> list[httpx.Request]:
    return []


def _client(redis: RedisClient, clock, requests: list[httpx.Request]) -> AeroApiClient:
    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"scheduled_arrivals": [], "num_pages": 1})

    budget = AeroApiBudget(redis, daily_cap=25, per_minute_cap=8, clock=clock)
    return AeroApiClient(
        "test-key", budget, "KBOS", transport=httpx.MockTransport(record), clock=clock
    )


async def test_budget_denies_when_redis_is_down(unreachable_redis: RedisClient, clock) -> None:
    budget = AeroApiBudget(unreachable_redis, daily_cap=25, per_minute_cap=8, clock=clock)

    assert await budget.reserve("scheduled_arrivals", 1) == BudgetDenial.REDIS_ERROR


async def test_client_sends_no_request_when_redis_is_down(
    unreachable_redis: RedisClient, clock, aeroapi_requests: list[httpx.Request]
) -> None:
    client = _client(unreachable_redis, clock, aeroapi_requests)

    outcome = await client.fetch_board(
        BoardEndpoint.SCHEDULED_ARRIVALS, clock(), clock() + 3600, max_pages=1
    )

    assert outcome == BudgetDenial.REDIS_ERROR
    assert aeroapi_requests == []


async def test_gate_is_closed_when_redis_is_down(unreachable_redis: RedisClient, clock) -> None:
    gate = EnrichmentGate(unreachable_redis, OPEN_CONFIG, clock=clock)

    assert await gate.evaluate() == GateReason.REDIS_ERROR


async def test_refresher_makes_no_calls_when_redis_is_down(
    unreachable_redis: RedisClient, clock, aeroapi_requests: list[httpx.Request]
) -> None:
    client = _client(unreachable_redis, clock, aeroapi_requests)
    gate = EnrichmentGate(unreachable_redis, OPEN_CONFIG, clock=clock)
    refresher = BoardRefresher(AirportBoard("KBOS"), client, gate, clock=clock)

    await refresher.tick()

    assert aeroapi_requests == []

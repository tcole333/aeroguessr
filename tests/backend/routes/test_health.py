"""Behaviour of the liveness (/healthz) and readiness (/readyz) probes."""

import asyncio
import contextlib
import json
import time
from typing import AsyncGenerator, Iterator

import fakeredis
import fakeredis.aioredis
import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx import AsyncClient

from backend.app import app
from backend.routes.rooms import get_redis
from backend.services import health as health_service
from backend.services.ingest_heartbeat import INGEST_HEARTBEAT_KEY
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def write_heartbeat(client: RedisClient, *, ts: float, feed_connected: bool = True) -> None:
    """Store a heartbeat in the wire format the ingest process writes."""
    await client.set(INGEST_HEARTBEAT_KEY, json.dumps({"ts": ts, "feed_connected": feed_connected}))


@contextlib.contextmanager
def serving_redis(client: RedisClient) -> Iterator[None]:
    """Make the app's get_redis dependency return ``client``."""
    original = app.dependency_overrides.get(get_redis)

    async def override() -> RedisClient:
        return client

    app.dependency_overrides[get_redis] = override
    try:
        yield
    finally:
        if original is None:
            app.dependency_overrides.pop(get_redis, None)
        else:
            app.dependency_overrides[get_redis] = original


@pytest.fixture
def unreachable_redis() -> Iterator[None]:
    server = fakeredis.FakeServer()
    server.connected = False
    with serving_redis(RedisClient(fakeredis.aioredis.FakeRedis(server=server))):
        yield


@pytest_asyncio.fixture
async def hung_redis(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None, None]:
    """A 'Redis' that accepts connections and never answers."""
    monkeypatch.setattr(health_service, "READINESS_REDIS_TIMEOUT_SECONDS", 0.1)
    server = await asyncio.start_server(lambda _r, _w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    connection = redis.Redis(host="127.0.0.1", port=port)
    try:
        with serving_redis(RedisClient(connection)):
            yield
    finally:
        await connection.aclose()
        server.close()


async def test_liveness_is_ok_without_redis_or_ingest(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liveness must not depend on Redis, whichever RedisClient instance is used."""

    async def no_redis(_self: RedisClient) -> None:
        raise redis.ConnectionError("Redis is down")

    monkeypatch.setattr(RedisClient, "get_connection", no_redis)

    response = await test_client.get("/healthz")

    assert (response.status_code, response.json()["status"]) == (200, "ok")


async def test_ready_with_fresh_heartbeat_and_no_planes(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """A quiet sky (no plane keys at all) is a normal, ready state."""
    await write_heartbeat(redis_client, ts=time.time())

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]) == (
        200,
        {"redis": "ok", "ingest": "ok"},
    )


async def test_not_ready_when_ingest_never_heartbeated(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (503, "down")


async def test_not_ready_when_heartbeat_is_stale(
    test_client: AsyncClient, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(health_service, "PROCESS_STARTED_TS", 0.0)
    threshold = health_service.INGEST_HEALTH_THRESHOLD_SECONDS
    await write_heartbeat(redis_client, ts=time.time() - threshold - 1)

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (503, "stale")


async def test_not_ready_when_heartbeat_predates_this_api_process(
    test_client: AsyncClient, redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A heartbeat left in Redis by a previous run says nothing about current ingest."""
    now = time.time()
    monkeypatch.setattr(health_service, "PROCESS_STARTED_TS", now - 1)
    await write_heartbeat(redis_client, ts=now - 5)

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (503, "down")


async def test_not_ready_when_heartbeat_is_dated_in_the_future(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    await write_heartbeat(redis_client, ts=time.time() + 3600)

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (503, "down")


async def test_not_ready_when_ingest_lost_its_feed(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    await write_heartbeat(redis_client, ts=time.time(), feed_connected=False)

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (
        503,
        "feed_disconnected",
    )


async def test_not_ready_when_heartbeat_is_unreadable(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    await redis_client.set(INGEST_HEARTBEAT_KEY, "not-json")

    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (503, "down")


async def test_not_ready_when_redis_unreachable(
    test_client: AsyncClient, unreachable_redis: None
) -> None:
    response = await test_client.get("/readyz")

    assert (response.status_code, response.json()["checks"]) == (
        503,
        {"redis": "down", "ingest": "unknown"},
    )


async def test_not_ready_promptly_when_redis_hangs(
    test_client: AsyncClient, hung_redis: None
) -> None:
    response = await asyncio.wait_for(test_client.get("/readyz"), timeout=2)

    assert (response.status_code, response.json()["checks"]["redis"]) == (503, "down")


async def test_not_ready_response_explains_why(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    response = await test_client.get("/readyz")

    assert response.json() == {
        "status": "not_ready",
        "checks": {"redis": "ok", "ingest": "down"},
        "reason": "No ingest heartbeat in Redis; is ingest running?",
        "ingest_heartbeat_age_seconds": None,
    }

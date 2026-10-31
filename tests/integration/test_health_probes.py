"""Readiness signals against a real Redis.

Uses the shared ``real_redis`` / ``real_redis_client`` fixtures from tests/conftest.py,
so it needs ``TEST_REDIS_URL`` on a dedicated non-zero db (see tests/README.md).
``real_redis_client`` also points ``REDIS_URL`` at that db, so the ``RedisClient``
the ingest loop creates talks to it too.
"""

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable, List, Optional

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis

from backend.app import app
from backend.ingest import main as ingest_main
from backend.routes.rooms import get_redis
from backend.services import ingest_heartbeat
from backend.services.ingest_heartbeat import (
    INGEST_HEARTBEAT_KEY,
    INGEST_HEARTBEAT_TTL_SECONDS,
    FeedStatus,
    IngestHeartbeat,
    publish_heartbeat,
    read_heartbeat,
)
from backend.utils.redis_async import RedisClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_published_heartbeat_reads_back_feed_state(real_redis_client: RedisClient) -> None:
    before = time.time()

    await publish_heartbeat(real_redis_client, FeedStatus(connected=True))

    heartbeat = await read_heartbeat(real_redis_client)
    assert heartbeat is not None
    assert heartbeat.feed_connected is True
    assert heartbeat.ts >= before


async def test_published_heartbeat_expires(
    real_redis_client: RedisClient, real_redis: redis.Redis
) -> None:
    await publish_heartbeat(real_redis_client, FeedStatus(connected=True))

    assert 0 < await real_redis.ttl(INGEST_HEARTBEAT_KEY) <= INGEST_HEARTBEAT_TTL_SECONDS


class SilentFeed:
    """A local ADS-B feed that accepts connections and sends nothing (a quiet sky)."""

    def __init__(self) -> None:
        self._server: Optional[asyncio.Server] = None
        self._clients: List[asyncio.StreamWriter] = []

    async def start(self) -> int:
        async def hold_open(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            self._clients.append(writer)

        self._server = await asyncio.start_server(hold_open, "127.0.0.1", 0)
        return self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        for writer in self._clients:
            writer.close()
        await self._server.wait_closed()


@dataclass
class RunningIngest:
    feed: SilentFeed
    task: "asyncio.Task[None]"

    async def stop(self) -> None:
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task


@pytest_asyncio.fixture
async def running_ingest(
    real_redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[RunningIngest, None]:
    """Run the real ingest loop against a silent local feed, on the test database."""
    monkeypatch.delenv("FAKE_ADSB", raising=False)
    monkeypatch.setattr(ingest_heartbeat, "INGEST_HEARTBEAT_INTERVAL_SECONDS", 0.05)
    feed = SilentFeed()
    monkeypatch.setattr(ingest_main, "ADSB_HOST", "127.0.0.1")
    monkeypatch.setattr(ingest_main, "ADSB_PORT", await feed.start())

    ingest = RunningIngest(feed=feed, task=asyncio.create_task(ingest_main.run_ingest_loop()))
    try:
        yield ingest
    finally:
        await ingest.stop()
        await feed.stop()


async def wait_for_heartbeat(
    redis_client: RedisClient,
    predicate: Callable[[IngestHeartbeat], bool],
    timeout: float = 3.0,
) -> Optional[IngestHeartbeat]:
    """Poll until a heartbeat matching ``predicate`` appears; None on timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        heartbeat = await read_heartbeat(redis_client)
        if heartbeat is not None and predicate(heartbeat):
            return heartbeat
        await asyncio.sleep(0.02)
    return None


async def test_ingest_heartbeat_stops_when_ingest_stops(
    running_ingest: RunningIngest, real_redis_client: RedisClient, real_redis: redis.Redis
) -> None:
    assert await wait_for_heartbeat(real_redis_client, lambda hb: hb.feed_connected) is not None

    await running_ingest.stop()
    await asyncio.sleep(0.1)  # let any in-flight publish finish
    await real_redis.delete(INGEST_HEARTBEAT_KEY)
    await asyncio.sleep(0.25)  # five heartbeat intervals

    assert await real_redis.exists(INGEST_HEARTBEAT_KEY) == 0


@pytest_asyncio.fixture
async def api(real_redis_client: RedisClient) -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for the API app, with its Redis dependency on the test db."""

    async def use_real_redis() -> RedisClient:
        return real_redis_client

    app.dependency_overrides[get_redis] = use_real_redis
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_redis, None)


async def test_not_ready_without_ingest(api: httpx.AsyncClient) -> None:
    response = await api.get("/readyz")

    assert (response.status_code, response.json()["checks"]) == (
        503,
        {"redis": "ok", "ingest": "down"},
    )


async def test_ready_while_ingest_is_on_a_quiet_feed(
    running_ingest: RunningIngest, real_redis_client: RedisClient, api: httpx.AsyncClient
) -> None:
    """Ingest connected to a feed that sends nothing: no planes, but ready."""
    assert await wait_for_heartbeat(real_redis_client, lambda hb: hb.feed_connected) is not None

    response = await api.get("/readyz")

    assert (response.status_code, response.json()["status"]) == (200, "ready")


async def test_not_ready_after_ingest_loses_its_feed(
    running_ingest: RunningIngest, real_redis_client: RedisClient, api: httpx.AsyncClient
) -> None:
    assert await wait_for_heartbeat(real_redis_client, lambda hb: hb.feed_connected) is not None
    await running_ingest.feed.stop()
    assert await wait_for_heartbeat(real_redis_client, lambda hb: not hb.feed_connected) is not None

    response = await api.get("/readyz")

    assert (response.status_code, response.json()["checks"]["ingest"]) == (
        503,
        "feed_disconnected",
    )

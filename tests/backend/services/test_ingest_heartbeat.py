"""Tests for the ingest heartbeat publisher used by the readiness probe."""

import asyncio

import fakeredis
import fakeredis.aioredis
import pytest

from backend.services import ingest_heartbeat
from backend.services.ingest_heartbeat import (
    INGEST_HEARTBEAT_KEY,
    FeedStatus,
    publish_heartbeat,
    read_heartbeat,
    start_heartbeat,
)
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def test_publish_failure_is_swallowed() -> None:
    """A Redis outage must never crash the ingest process."""
    server = fakeredis.FakeServer()
    server.connected = False
    client = RedisClient(fakeredis.aioredis.FakeRedis(server=server))

    await publish_heartbeat(client, FeedStatus(connected=True))


async def test_heartbeats_stop_when_owning_task_ends(
    redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ingest_heartbeat, "INGEST_HEARTBEAT_INTERVAL_SECONDS", 0.01)

    async def short_lived_ingest() -> None:
        start_heartbeat(redis_client).connected = True
        await asyncio.sleep(0.05)

    await asyncio.create_task(short_lived_ingest())
    heartbeat = await read_heartbeat(redis_client)
    assert heartbeat is not None and heartbeat.feed_connected

    await asyncio.sleep(0.02)  # let any in-flight publish finish
    await redis_client.delete(INGEST_HEARTBEAT_KEY)
    await asyncio.sleep(0.1)  # ten heartbeat intervals
    assert await read_heartbeat(redis_client) is None

"""Tests for the presence and activity signals used to gate enrichment costs."""

from typing import Optional

import pytest

from backend.services.presence import (
    ACTIVE_ROOMS_KEY,
    ACTIVITY_TTL_SECONDS,
    LAST_ACTIVITY_KEY,
    PRESENCE_TTL_SECONDS,
    PresenceSnapshot,
    publish_active_rooms,
    read_presence,
    record_gameplay_activity,
)
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


class _FakeRedisClient:
    """Minimal stand-in matching the RedisClient.get/set surface used here."""

    def __init__(self) -> None:
        self.store: dict = {}
        self.last_expire = None
        self.fail = False

    async def set(self, key: str, value: str, expire_seconds: Optional[int] = None) -> bool:
        if self.fail:
            raise RuntimeError("redis down")
        self.store[key] = str(value)
        self.last_expire = expire_seconds
        return True

    async def get(self, key: str) -> Optional[str]:
        if self.fail:
            raise RuntimeError("redis down")
        return self.store.get(key)


async def test_publish_then_read_active() -> None:
    client = _FakeRedisClient()
    await publish_active_rooms(client, 2)
    assert client.store[ACTIVE_ROOMS_KEY] == "2"
    assert client.last_expire == PRESENCE_TTL_SECONDS
    assert (await read_presence(client)).active_rooms == 2


async def test_zero_rooms_is_inactive() -> None:
    client = _FakeRedisClient()
    await publish_active_rooms(client, 0)
    assert (await read_presence(client)).active_rooms == 0


async def test_publish_failure_is_swallowed() -> None:
    """Publishing must never crash the broadcast loop on a transient Redis error."""
    client = _FakeRedisClient()
    client.fail = True
    await publish_active_rooms(client, 3)  # should not raise


# --- Gameplay activity + presence snapshot (read by the enrichment gate) ---


async def test_recorded_activity_is_read_back_with_ttl(redis_client: RedisClient) -> None:
    await record_gameplay_activity(redis_client, now=1_700_000_000.5)

    snapshot = await read_presence(redis_client)
    conn = await redis_client.get_connection()
    assert snapshot.last_activity_ts == 1_700_000_000.5
    assert 0 < await conn.ttl(LAST_ACTIVITY_KEY) <= ACTIVITY_TTL_SECONDS


async def test_presence_snapshot_reports_active_rooms(redis_client: RedisClient) -> None:
    await publish_active_rooms(redis_client, 3)
    assert (await read_presence(redis_client)).active_rooms == 3


async def test_presence_snapshot_defaults_when_keys_missing(redis_client: RedisClient) -> None:
    assert await read_presence(redis_client) == PresenceSnapshot(
        active_rooms=0, last_activity_ts=None
    )


@pytest.mark.parametrize("garbage", ["not-a-number", "nan", "inf"])
async def test_presence_snapshot_ignores_unparseable_values(
    redis_client: RedisClient, garbage: str
) -> None:
    await redis_client.set(ACTIVE_ROOMS_KEY, garbage)
    await redis_client.set(LAST_ACTIVITY_KEY, garbage)
    assert await read_presence(redis_client) == PresenceSnapshot(
        active_rooms=0, last_activity_ts=None
    )


async def test_presence_read_failure_propagates() -> None:
    """The gate must see Redis errors so it can fail closed."""
    client = _FakeRedisClient()
    client.fail = True
    with pytest.raises(RuntimeError):
        await read_presence(client)


async def test_activity_record_failure_is_swallowed() -> None:
    """Recording activity must never break gameplay on a transient Redis error."""
    client = _FakeRedisClient()
    client.fail = True
    await record_gameplay_activity(client)  # should not raise

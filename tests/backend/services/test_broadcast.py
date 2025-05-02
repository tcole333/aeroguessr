from typing import Dict

import pytest
from fakeredis import aioredis

from backend.ingest.main import PlaneState
from backend.services.broadcast import _get_current_plane_state_map
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def _prepare_dummy_planes(conn: aioredis.FakeRedis, mapping: Dict[str, PlaneState]) -> None:
    """Helper to seed plane:* keys into Redis."""
    for hex_ident, plane in mapping.items():
        key = f"plane:{hex_ident}"
        await conn.set(key, plane.model_dump_json(), ex=60)


async def test_get_current_plane_state_map_returns_all_planes() -> None:
    """Ensure helper returns a correct mapping even with decode_responses pool.

    This specifically guards against the redis-py ``scan_iter`` hang (GH-2389)
    that motivated the manual paging implementation.
    """

    # Use fakeredis pool with decode_responses=True to mimic production.
    fake_redis = aioredis.FakeRedis(decode_responses=True)
    client = RedisClient(redis_instance=fake_redis)

    # Seed two dummy planes.
    planes = {
        "a1b2c3": PlaneState(
            hex_ident="a1b2c3",
            lat=42.0,
            lon=-71.0,
            alt=18000,
            lat_v=0,
            lon_v=0,
            alt_v=0,
            last_update_ts=123.0,
            trail=[],
        ),
        "d4e5f6": PlaneState(
            hex_ident="d4e5f6",
            lat=43.0,
            lon=-72.0,
            alt=20000,
            lat_v=0,
            lon_v=0,
            alt_v=0,
            last_update_ts=124.0,
            trail=[],
        ),
    }
    async with fake_redis as conn:
        await _prepare_dummy_planes(conn, planes)

    # Act
    state_map = await _get_current_plane_state_map(client)

    # Assert – order not important
    assert set(state_map.keys()) == set(planes.keys())
    for hex_ident, plane in planes.items():
        assert state_map[hex_ident] == plane

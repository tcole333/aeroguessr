import asyncio
import json
import time
from typing import Dict

import pytest
from fakeredis import aioredis

from backend.schemas.plane import PlaneState, RouteHint
from backend.schemas.ws import DeltaPayload
from backend.services.broadcast import (
    _get_current_plane_state_map,
    broadcast_plane_updates,
    build_plane_delta_message,
)
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient


async def _prepare_dummy_planes(conn: aioredis.FakeRedis, mapping: Dict[str, PlaneState]) -> None:
    """Helper to seed plane:* keys into Redis."""
    for hex_ident, plane in mapping.items():
        key = f"plane:{hex_ident}"
        await conn.set(key, plane.model_dump_json(), ex=60)


@pytest.mark.asyncio
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


def _plane(hex_ident: str, origin: str | None, destination: str | None) -> PlaneState:
    """A plane over Logan with a fresh timestamp, so the broadcast loop keeps it."""
    return PlaneState(
        hex_ident=hex_ident,
        lat=42.3656,
        lon=-71.0096,
        alt=12000,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=time.time(),
        callsign="UAL123",
        operator="United",
        origin=origin,
        destination=destination,
    )


def test_plane_delta_message_carries_route_hints() -> None:
    message = build_plane_delta_message(
        [_plane("dep1", "KBOS", "KJFK")], ["gone1"], monitored_airport="KBOS"
    )

    payload = DeltaPayload.model_validate(message["payload"])
    (plane,) = payload.planes["updated"]
    assert (message["type"], payload.planes["removed"]) == ("delta", ["gone1"])
    assert plane.route_hint == RouteHint(
        guess_direction="destination", known_airport="KBOS", eligible=True
    )
    assert (plane.callsign, plane.operator) == ("UAL123", "United")


class _CapturingSocket:
    """Stands in for a client WebSocket and keeps every frame as it would go on the wire."""

    client = "capture"

    def __init__(self) -> None:
        self.frames: list[str] = []
        self.delta_sent = asyncio.Event()

    async def accept(self) -> None:
        return None

    async def send_json(self, message: dict) -> None:
        self.frames.append(json.dumps(message))
        if message.get("type") == "delta":
            self.delta_sent.set()


async def _first_broadcast_delta(plane: PlaneState) -> str:
    """Run the real broadcast loop over ``plane`` and return its first delta frame."""
    fake_redis = aioredis.FakeRedis(decode_responses=True)
    await fake_redis.set(f"plane:{plane.hex_ident}", plane.model_dump_json(), ex=60)
    manager = ConnectionManager()
    socket = _CapturingSocket()
    await manager.connect(socket, "ROOM", "Player")  # type: ignore[arg-type]

    loop_task = asyncio.create_task(
        broadcast_plane_updates(RedisClient(redis_instance=fake_redis), manager)
    )
    try:
        await asyncio.wait_for(socket.delta_sent.wait(), timeout=5)
    finally:
        loop_task.cancel()
        await asyncio.gather(loop_task, return_exceptions=True)
        await fake_redis.aclose()

    return next(frame for frame in socket.frames if json.loads(frame)["type"] == "delta")


@pytest.mark.asyncio
async def test_broadcast_loop_sends_planes_with_route_hints() -> None:
    frame = await _first_broadcast_delta(_plane("loop1", "KJFK", "KBOS"))

    (plane,) = json.loads(frame)["payload"]["planes"]["updated"]
    assert plane["route_hint"] == {
        "guess_direction": "origin",
        "known_airport": "KBOS",
        "eligible": True,
    }


def test_plane_delta_message_hides_every_route_airport() -> None:
    message = build_plane_delta_message(
        [_plane("dep2", "KBOS", "KJFK"), _plane("over1", "KLAX", "KSFO")], [], "KBOS"
    )

    wire = json.dumps(message)
    assert [code for code in ("JFK", "LAX", "SFO") if code in wire] == []


@pytest.mark.asyncio
async def test_broadcast_loop_never_sends_the_answer() -> None:
    frame = await _first_broadcast_delta(_plane("loop2", "KJFK", "KBOS"))

    (plane,) = json.loads(frame)["payload"]["planes"]["updated"]
    assert ("JFK" in frame, {"origin", "destination"} & plane.keys()) == (False, set())

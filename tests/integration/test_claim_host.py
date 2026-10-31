"""Integration tests for claiming host after the host has left an otherwise empty room.

When the host leaves while other players are connected, the server hands the role over
immediately. Only a host who leaves alone starts the claim window
(HOST_DISCONNECT_CLAIM_WINDOW_SECONDS), so each test here empties the room first.
"""

import asyncio
import os
import time
import uuid

import httpx
import pytest
import redis.asyncio as redis
from httpx_ws import aconnect_ws

from backend.schemas.core import RoomMeta
from backend.schemas.ws import ErrorCode

from .ws_helpers import wait_for_message

pytestmark = pytest.mark.integration

CLAIM_WINDOW_ENV = "HOST_DISCONNECT_CLAIM_WINDOW_SECONDS"
DISCONNECT_RECORDED_TIMEOUT_SECONDS = 5.0


@pytest.fixture
def claim_window_seconds() -> float:
    """The claim window the backend under test was started with."""
    value = os.environ.get(CLAIM_WINDOW_ENV)
    if not value:
        pytest.fail(
            f"{CLAIM_WINDOW_ENV} is not set. Export the same value the backend under test was "
            "started with (CI and docker-compose.test.yml use 2).",
            pytrace=False,
        )
    return float(value)


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


async def _read_meta(redis_conn: redis.Redis, room_code: str) -> RoomMeta:
    meta_json = await redis_conn.get(f"room:{room_code}:meta")
    assert meta_json is not None, f"room:{room_code}:meta is missing"
    return RoomMeta.model_validate_json(meta_json)


async def _create_room_with_claimer(client: httpx.AsyncClient) -> tuple[str, str, str]:
    """Create a room and join a second player over REST; return (room, host, claimer)."""
    host_nick, claimer_nick = _unique("host"), _unique("claimer")
    create = await client.post(
        "/api/v0/rooms",
        json={"host_nickname": host_nick, "mode": "Distance", "round_timeout_seconds": 10},
    )
    create.raise_for_status()
    room_code = create.json()["room_code"]
    join = await client.post(f"/api/v0/rooms/{room_code}/join", json={"nickname": claimer_nick})
    join.raise_for_status()
    return room_code, host_nick, claimer_nick


async def _host_leaves_empty_room(
    client: httpx.AsyncClient, redis_conn: redis.Redis, room_code: str, host_nick: str
) -> float:
    """Connect the host alone, leave, and return the host_disconnected_ts the server records."""
    async with aconnect_ws(f"/api/v0/rooms/ws/{room_code}/{host_nick}", client) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        await host_ws.send_json({"type": "leave", "payload": {}})

    deadline = time.monotonic() + DISCONNECT_RECORDED_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        meta = await _read_meta(redis_conn, room_code)
        if meta.host_disconnected_ts is not None:
            return meta.host_disconnected_ts
        await asyncio.sleep(0.05)
    pytest.fail(
        f"Server did not record host_disconnected_ts for room {room_code} within "
        f"{DISCONNECT_RECORDED_TIMEOUT_SECONDS}s of the host leaving."
    )


@pytest.mark.asyncio
async def test_claim_host_rejected_while_host_connected(
    integration_client: httpx.AsyncClient,
) -> None:
    room_code, host_nick, claimer_nick = await _create_room_with_claimer(integration_client)

    async with aconnect_ws(
        f"/api/v0/rooms/ws/{room_code}/{host_nick}", integration_client
    ) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        async with aconnect_ws(
            f"/api/v0/rooms/ws/{room_code}/{claimer_nick}", integration_client
        ) as claimer_ws:
            await wait_for_message(claimer_ws, "stateSync")

            await claimer_ws.send_json({"type": "claimHost", "payload": {}})

            await wait_for_message(
                claimer_ws, "error", code=ErrorCode.CLAIM_HOST_STILL_CONNECTED.value
            )


@pytest.mark.asyncio
async def test_claim_host_rejected_before_window_opens(
    integration_client: httpx.AsyncClient,
    real_redis: redis.Redis,
    claim_window_seconds: float,
) -> None:
    room_code, host_nick, claimer_nick = await _create_room_with_claimer(integration_client)
    disconnected_ts = await _host_leaves_empty_room(
        integration_client, real_redis, room_code, host_nick
    )

    async with aconnect_ws(
        f"/api/v0/rooms/ws/{room_code}/{claimer_nick}", integration_client
    ) as claimer_ws:
        await wait_for_message(claimer_ws, "stateSync")
        assert time.time() < disconnected_ts + claim_window_seconds, (
            "The claim window opened before the claim could be sent, so this run cannot test "
            f"the early rejection; {CLAIM_WINDOW_ENV} is too short for this machine."
        )
        await claimer_ws.send_json({"type": "claimHost", "payload": {}})

        await wait_for_message(claimer_ws, "error", code=ErrorCode.CLAIM_HOST_TOO_EARLY.value)

    meta = await _read_meta(real_redis, room_code)
    assert meta.host_nickname == host_nick


@pytest.mark.asyncio
async def test_claim_host_succeeds_after_window(
    integration_client: httpx.AsyncClient,
    real_redis: redis.Redis,
    claim_window_seconds: float,
) -> None:
    room_code, host_nick, claimer_nick = await _create_room_with_claimer(integration_client)
    disconnected_ts = await _host_leaves_empty_room(
        integration_client, real_redis, room_code, host_nick
    )

    async with aconnect_ws(
        f"/api/v0/rooms/ws/{room_code}/{claimer_nick}", integration_client
    ) as claimer_ws:
        await wait_for_message(claimer_ws, "stateSync")
        await asyncio.sleep(max(0.0, disconnected_ts + claim_window_seconds + 0.25 - time.time()))
        await claimer_ws.send_json({"type": "claimHost", "payload": {}})

        await wait_for_message(claimer_ws, "newHost", nickname=claimer_nick)

    meta = await _read_meta(real_redis, room_code)
    assert meta.host_nickname == claimer_nick

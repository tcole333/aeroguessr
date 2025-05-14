# ruff: noqa: D101, D103
"""Integration tests ensuring the server ends rounds correctly.

These tests cover the two main paths that should trigger a `roundResult`:
1. Timer expiry when not all players have guessed.
2. All connected players submitting guesses before the timer expires.

Both tests assume the backend-test service and redis-test service are running via
`infra/docker-compose.test.yml` (executed by `make integration-test`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.ingest.main import PlaneState
from backend.schemas.core import ScoringMode
from backend.schemas.game import RoundData, RoundStateEnum
from backend.schemas.ws import (
    GuessPayload,
    PingPongPayload,
    RoundResultPayload,
    SelectPlanePayload,
    WSMessage,
)

pytestmark = pytest.mark.integration
logger = logging.getLogger(__name__)


async def _wait_for_message(
    # ruff: noqa
    ws: Any,  # httpx_ws.AsyncWebSocketSession but keep generic to avoid import issues
    target_type: str,
    timeout: float = 15.0,
) -> WSMessage:
    """Consume WS frames until `target_type` is received.

    Automatically responds to `ping` messages to keep the connection alive.
    """

    end_time = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = end_time - asyncio.get_event_loop().time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timeout waiting for WS message '{target_type}'.")

        raw = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        msg = WSMessage(**raw)
        if msg.type == "ping":
            # Echo pong
            ping_payload = PingPongPayload(**msg.payload)
            pong = WSMessage(type="pong", payload=ping_payload.model_dump())
            await ws.send_json(pong.model_dump())
            continue
        if msg.type == target_type:
            return msg
        # For tests we silently ignore other types (e.g., delta) – could be logged


@pytest.mark.asyncio
async def test_round_timeout_triggers_result(
    integration_client: AsyncClient, integration_redis: redis.Redis
) -> None:
    """Host-only room ‑ expect `roundResult` after timer expires."""
    host_nick = "host_timeout"
    plane_hex = "deadbe"
    timeout_s = 10  # Minimum allowed by schema

    # — Create room
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": timeout_s,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]

    # — Insert dummy plane state into Redis
    plane_key = f"plane:{plane_hex}"
    dummy_plane = PlaneState(
        hex_ident=plane_hex,
        lat=42.0,
        lon=-71.0,
        alt=30000,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=time.time(),
        trail=[],
        origin="KLAX",
        destination="KJFK",
        callsign=None,
        origin_country=None,
        category=None,
    )
    await integration_redis.set(plane_key, dummy_plane.model_dump_json(), ex=60)

    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"

    async with aconnect_ws(ws_path, client=integration_client) as ws_host:
        # Consume initial stateSync
        await ws_host.receive_json()

        # Select plane then start round
        select_payload = SelectPlanePayload(hex=plane_hex)
        await ws_host.send_json(
            WSMessage(type="selectPlane", payload=select_payload.model_dump()).model_dump()
        )
        await asyncio.sleep(0.1)
        await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())

        # Wait for roundStart broadcast then for roundResult
        await _wait_for_message(ws_host, "roundStart", timeout=2.0)
        result_msg = await _wait_for_message(ws_host, "roundResult", timeout=timeout_s + 5)

    # Validate payload
    result_payload = RoundResultPayload(**result_msg.payload)
    assert len(result_payload.results) == 1  # Only host in room

    # Validate Redis state
    round_key = f"room:{room_code}:round"
    stored_json = await integration_redis.get(round_key)
    assert stored_json is not None
    stored_round = RoundData(**json.loads(stored_json))
    assert stored_round.state == RoundStateEnum.SHOWING_RESULTS

    # Cleanup
    await integration_redis.delete(plane_key)
    await integration_redis.delete(f"room:{room_code}:meta")
    await integration_redis.delete(f"room:{room_code}:players")
    await integration_redis.delete(round_key)


@pytest.mark.asyncio
async def test_round_result_when_all_players_guessed(
    integration_client: AsyncClient, integration_redis: redis.Redis
) -> None:
    """Host + 1 player both guess quickly ─ expect early `roundResult`."""
    host_nick = "host_all"
    player_nick = "player_all"
    plane_hex = "c0ffee"
    timeout_s = 10

    # Create room
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": timeout_s,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]

    # Player joins via REST
    resp2 = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": player_nick}
    )
    assert resp2.status_code == status.HTTP_200_OK

    # Dummy plane
    plane_key = f"plane:{plane_hex}"
    await integration_redis.set(
        plane_key,
        PlaneState(
            hex_ident=plane_hex,
            lat=50.0,
            lon=8.0,
            alt=32000,
            lat_v=0,
            lon_v=0,
            alt_v=0,
            last_update_ts=time.time(),
            trail=[],
            origin="EDDF",
            destination="EGLL",
            callsign=None,
            origin_country=None,
            category=None,
        ).model_dump_json(),
        ex=60,
    )

    ws_host_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_player_path = f"/api/v0/rooms/ws/{room_code}/{player_nick}"

    async with (
        aconnect_ws(ws_host_path, client=integration_client) as ws_host,
        aconnect_ws(ws_player_path, client=integration_client) as ws_player,
    ):
        # Consume initial syncs & playerJoined
        await ws_host.receive_json()
        await ws_player.receive_json()
        await _wait_for_message(ws_host, "playerJoined", timeout=2.0)

        # Host selects plane & starts round
        await ws_host.send_json(
            WSMessage(type="selectPlane", payload={"hex": plane_hex}).model_dump()
        )
        await asyncio.sleep(0.1)
        await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())
        await _wait_for_message(ws_host, "roundStart", timeout=2.0)
        await _wait_for_message(ws_player, "roundStart", timeout=2.0)

        # Both players guess
        await ws_player.send_json(
            WSMessage(
                type="guess", payload=GuessPayload(airport_code="BOS").model_dump()
            ).model_dump()
        )
        await ws_host.send_json(
            WSMessage(
                type="guess", payload=GuessPayload(airport_code="BOS").model_dump()
            ).model_dump()
        )

        # Expect roundResult quickly (< 3 s)
        result_host = await _wait_for_message(ws_host, "roundResult", timeout=5.0)
        # Accept delta message in any order
        payload_host = RoundResultPayload(**result_host.payload)
        assert {res.nickname for res in payload_host.results} == {host_nick, player_nick}

    # Check Redis state & scores
    round_key = f"room:{room_code}:round"
    stored_json = await integration_redis.get(round_key)
    assert stored_json is not None
    rd = RoundData(**json.loads(stored_json))
    assert rd.state == RoundStateEnum.SHOWING_RESULTS
    assert rd.results is not None

    await integration_redis.delete(plane_key)
    await integration_redis.delete(f"room:{room_code}:meta")
    await integration_redis.delete(f"room:{room_code}:players")
    await integration_redis.delete(round_key)

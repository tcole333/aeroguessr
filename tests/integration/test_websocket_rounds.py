# ruff: noqa: D101, D103
"""Integration tests ensuring the server ends rounds correctly.

These tests cover the two main paths that should trigger a `roundResult`:
1. Timer expiry when not all players have guessed.
2. All connected players submitting guesses before the timer expires.

They run against a live backend and real Redis; see tests/README.md.
"""

from __future__ import annotations

import json

import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, aconnect_ws

from backend.schemas.core import ScoringMode
from backend.schemas.game import RoundData, RoundStateEnum
from backend.schemas.ws import GuessPayload, RoundResultPayload, WSMessage

from .planes import seed_plane
from .ws_helpers import Expected, wait_for_message, wait_for_messages

pytestmark = pytest.mark.integration


async def _create_room(
    client: AsyncClient, host_nick: str, mode: ScoringMode, *player_nicks: str
) -> str:
    resp = await client.post(
        "/api/v0/rooms",
        json={"host_nickname": host_nick, "mode": mode.value, "round_timeout_seconds": 10},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    for nick in player_nicks:
        join = await client.post(f"/api/v0/rooms/{room_code}/join", json={"nickname": nick})
        assert join.status_code == status.HTTP_200_OK
    return room_code


async def _start_round(ws_host: AsyncWebSocketSession, plane_hex: str) -> None:
    await ws_host.send_json(WSMessage(type="selectPlane", payload={"hex": plane_hex}).model_dump())
    await wait_for_message(ws_host, "planeSelectedConfirm", hex=plane_hex)
    await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())


async def _send_guess(ws: AsyncWebSocketSession, airport_code: str) -> None:
    guess = WSMessage(type="guess", payload=GuessPayload(airport_code=airport_code).model_dump())
    await ws.send_json(guess.model_dump())


async def _read_round(redis_conn: redis.Redis, room_code: str) -> RoundData:
    stored_json = await redis_conn.get(f"room:{room_code}:round")
    assert stored_json is not None
    return RoundData(**json.loads(stored_json))


@pytest.mark.asyncio
async def test_round_timeout_triggers_result(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Host-only room ‑ expect `roundResult` after timer expires."""
    host_nick = "host_timeout"
    plane_hex = "deadbe"
    timeout_s = 10  # Minimum allowed by schema
    room_code = await _create_room(integration_client, host_nick, ScoringMode.EXACT)
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KLAX")

    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    async with aconnect_ws(ws_path, client=integration_client) as ws_host:
        await wait_for_message(ws_host, "stateSync")
        await _start_round(ws_host, plane_hex)
        await wait_for_message(ws_host, "roundStart")
        result_msg = await wait_for_message(ws_host, "roundResult", timeout=timeout_s + 5)

    result_payload = RoundResultPayload(**result_msg["payload"])
    assert len(result_payload.results) == 1  # Only host in room
    assert result_payload.hex == plane_hex

    stored_round = await _read_round(real_redis, room_code)
    assert stored_round.state == RoundStateEnum.SHOWING_RESULTS


@pytest.mark.asyncio
async def test_round_result_when_all_players_guessed(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Host + 1 player both guess quickly ─ expect early `roundResult`."""
    host_nick = "host_all"
    player_nick = "player_all"
    plane_hex = "c0ffee"
    room_code = await _create_room(integration_client, host_nick, ScoringMode.DISTANCE, player_nick)
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="EGLL")

    ws_host_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_player_path = f"/api/v0/rooms/ws/{room_code}/{player_nick}"
    async with (
        aconnect_ws(ws_host_path, client=integration_client) as ws_host,
        aconnect_ws(ws_player_path, client=integration_client) as ws_player,
    ):
        await wait_for_messages(
            ws_host, Expected("stateSync"), Expected("playerJoined", {"nickname": player_nick})
        )
        await wait_for_message(ws_player, "stateSync")

        await _start_round(ws_host, plane_hex)
        await wait_for_message(ws_host, "roundStart")
        await wait_for_message(ws_player, "roundStart")

        # Both players guess back to back, well inside the 10s timer.
        await _send_guess(ws_player, "BOS")
        await _send_guess(ws_host, "BOS")

        result_host = await wait_for_message(ws_host, "roundResult")

    payload_host = RoundResultPayload(**result_host["payload"])
    assert payload_host.hex == plane_hex
    assert {res.nickname for res in payload_host.results} == {host_nick, player_nick}
    assert all(res.guess == "BOS" for res in payload_host.results)

    rd = await _read_round(real_redis, room_code)
    assert rd.state == RoundStateEnum.SHOWING_RESULTS
    assert rd.results is not None


@pytest.mark.asyncio
async def test_round_result_includes_distance_km_in_distance_mode(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Test that distance_km is included in round results for Distance mode."""
    host_nick = "host_distance"
    player_nick = "player_distance"
    plane_hex = "abc123"
    room_code = await _create_room(integration_client, host_nick, ScoringMode.DISTANCE, player_nick)
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KJFK")

    ws_host_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_player_path = f"/api/v0/rooms/ws/{room_code}/{player_nick}"
    async with (
        aconnect_ws(ws_host_path, client=integration_client) as ws_host,
        aconnect_ws(ws_player_path, client=integration_client) as ws_player,
    ):
        await wait_for_messages(
            ws_host, Expected("stateSync"), Expected("playerJoined", {"nickname": player_nick})
        )
        await wait_for_message(ws_player, "stateSync")

        await _start_round(ws_host, plane_hex)
        await wait_for_message(ws_host, "roundStart")
        await wait_for_message(ws_player, "roundStart")

        # Host guesses the destination (0 km); the player guesses the origin (~300 km away).
        await _send_guess(ws_host, "KJFK")
        await _send_guess(ws_player, "KBOS")

        result_host = await wait_for_message(ws_host, "roundResult")

    payload_host = RoundResultPayload(**result_host["payload"])
    assert len(payload_host.results) == 2
    host_result = next(r for r in payload_host.results if r.nickname == host_nick)
    player_result = next(r for r in payload_host.results if r.nickname == player_nick)

    assert host_result.distance_km == 0.0
    assert host_result.score_awarded == 100

    # KBOS-KJFK great-circle distance is ~300 km.
    assert player_result.distance_km is not None
    assert 295 <= player_result.distance_km <= 305
    assert 0 <= player_result.score_awarded < 100  # Partial score


@pytest.mark.asyncio
async def test_round_result_no_distance_km_in_exact_mode(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Test that distance_km is None in round results for Exact mode."""
    host_nick = "host_exact"
    plane_hex = "def456"
    room_code = await _create_room(integration_client, host_nick, ScoringMode.EXACT)
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KJFK")

    ws_host_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    async with aconnect_ws(ws_host_path, client=integration_client) as ws_host:
        await wait_for_message(ws_host, "stateSync")
        await _start_round(ws_host, plane_hex)
        await wait_for_message(ws_host, "roundStart")

        await _send_guess(ws_host, "KJFK")
        result_msg = await wait_for_message(ws_host, "roundResult")

    payload = RoundResultPayload(**result_msg["payload"])
    assert len(payload.results) == 1
    host_result = payload.results[0]
    assert host_result.nickname == host_nick
    assert host_result.distance_km is None  # Exact mode reports no distance
    assert host_result.score_awarded == 100  # Exact match

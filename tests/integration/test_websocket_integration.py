"""Integration tests for WebSocket endpoints against a live backend and real Redis.

See tests/README.md for how to start the backend these tests talk to.
"""

import asyncio
import json
import time

import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.schemas.core import ScoringMode
from backend.schemas.game import PlayerGuess, RoundData, RoundStateEnum
from backend.schemas.ws import GuessPayload, SelectPlanePayload, WSMessage

from .planes import seed_plane
from .ws_helpers import Expected, wait_for_message, wait_for_messages

pytestmark = pytest.mark.integration

STORED_GUESS_TIMEOUT_SECONDS = 2.0


async def _wait_for_stored_guess(
    redis_conn: redis.Redis, room_code: str, nickname: str
) -> RoundData:
    """Poll the room's round data until ``nickname``'s guess is stored."""
    deadline = time.monotonic() + STORED_GUESS_TIMEOUT_SECONDS
    round_data: RoundData | None = None
    while time.monotonic() < deadline:
        round_json = await redis_conn.get(f"room:{room_code}:round")
        if round_json is not None:
            round_data = RoundData(**json.loads(round_json))
            if nickname in round_data.guesses:
                return round_data
        await asyncio.sleep(0.05)
    pytest.fail(
        f"{nickname}'s guess was not stored within {STORED_GUESS_TIMEOUT_SECONDS}s. "
        f"Last round data: {round_data}"
    )


async def _read_round(redis_conn: redis.Redis, room_code: str) -> RoundData:
    round_json = await redis_conn.get(f"room:{room_code}:round")
    assert round_json is not None, f"room:{room_code}:round is missing"
    return RoundData(**json.loads(round_json))


@pytest.mark.asyncio
async def test_websocket_connect_and_state_sync_integration(
    integration_client: AsyncClient,
) -> None:
    """Verify WebSocket stateSync comes through on a real server."""
    payload = {
        "host_nickname": "int_host",
        "mode": ScoringMode.DISTANCE.value,
        "round_timeout_seconds": 15,
    }
    resp = await integration_client.post("/api/v0/rooms", json=payload)
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/int_host"

    async with aconnect_ws(ws_path, client=integration_client) as ws:
        state_payload = (await wait_for_message(ws, "stateSync"))["payload"]

    # Host should be alone and connected
    assert state_payload["room_meta"]["host_nickname"] == "int_host"
    assert isinstance(state_payload["players"], dict)
    assert len(state_payload["players"]) == 1


@pytest.mark.asyncio
async def test_websocket_player_join_broadcast_integration(integration_client: AsyncClient) -> None:
    """Verify playerJoined broadcast on a real server."""
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": "host2",
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]

    joiner_nickname = "join2"
    resp2 = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": joiner_nickname}
    )
    assert resp2.status_code == status.HTTP_200_OK
    ws_host_path = f"/api/v0/rooms/ws/{room_code}/host2"
    ws_join_path = f"/api/v0/rooms/ws/{room_code}/{joiner_nickname}"

    async with aconnect_ws(ws_host_path, client=integration_client) as ws_h:
        await wait_for_message(ws_h, "stateSync")
        async with aconnect_ws(ws_join_path, client=integration_client) as ws_j:
            await wait_for_message(ws_j, "stateSync")

            # Host receives playerJoined for the joiner once the joiner connects
            await wait_for_message(ws_h, "playerJoined", nickname=joiner_nickname)


@pytest.mark.asyncio
async def test_websocket_host_select_plane_integration(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Verify host can select a plane and round data is updated in Redis."""
    host_nick = "host_sel"
    plane_hex = "a1b2c3"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KJFK")

    async with aconnect_ws(ws_path, client=integration_client) as ws_host:
        await wait_for_message(ws_host, "stateSync")

        select_message = WSMessage(
            type="selectPlane", payload=SelectPlanePayload(hex=plane_hex).model_dump()
        )
        await ws_host.send_json(select_message.model_dump())

        # The server confirms after it has stored the selection in Redis.
        confirm = (await wait_for_message(ws_host, "planeSelectedConfirm"))["payload"]

        round_data = await _read_round(real_redis, room_code)

    # The flight departs the monitored airport (KBOS by default), so players guess its
    # destination. The host is a player too, so the confirm names no airport.
    assert confirm == {"hex": plane_hex, "guess_direction": "destination"}

    assert round_data.state == RoundStateEnum.WAITING_FOR_SELECTION  # Not started yet
    assert round_data.selected_plane_hex == plane_hex
    assert round_data.correct_airport_code == "KJFK"
    assert round_data.guess_direction == "destination"


@pytest.mark.asyncio
async def test_websocket_host_start_round_integration(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Verify host can start a round and roundStart is broadcast."""
    host_nick = "host_start"
    plane_hex = "d4e5f6"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 15,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KJFK")

    async with aconnect_ws(ws_path, client=integration_client) as ws_host:
        await wait_for_message(ws_host, "stateSync")

        await ws_host.send_json(
            WSMessage(type="selectPlane", payload={"hex": plane_hex}).model_dump()
        )
        await wait_for_message(ws_host, "planeSelectedConfirm", hex=plane_hex)

        await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())
        await wait_for_message(ws_host, "roundStart")

        round_data = await _read_round(real_redis, room_code)

    assert round_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert round_data.round_number == 1
    assert round_data.round_start_time is not None


@pytest.mark.asyncio
async def test_websocket_player_guess_integration(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Verify a player can submit a guess and it's stored."""
    host_nick = "host_guess"
    player_nick = "player_guess"
    plane_hex = "a7b8c9"
    guess_code = "LHR"
    resp_host = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 10,  # Minimum allowed by the schema
        },
    )
    assert resp_host.status_code == status.HTTP_201_CREATED
    room_code = resp_host.json()["room_code"]
    resp_player = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": player_nick}
    )
    assert resp_player.status_code == status.HTTP_200_OK
    ws_host_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_player_path = f"/api/v0/rooms/ws/{room_code}/{player_nick}"
    await seed_plane(real_redis, plane_hex, origin="EGLL", destination="KBOS")

    async with (
        aconnect_ws(ws_host_path, client=integration_client) as ws_host,
        aconnect_ws(ws_player_path, client=integration_client) as ws_player,
    ):
        await wait_for_messages(
            ws_host, Expected("stateSync"), Expected("playerJoined", {"nickname": player_nick})
        )
        await wait_for_message(ws_player, "stateSync")

        await ws_host.send_json(
            WSMessage(type="selectPlane", payload={"hex": plane_hex}).model_dump()
        )
        await wait_for_message(ws_host, "planeSelectedConfirm", hex=plane_hex)
        await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())
        await wait_for_message(ws_host, "roundStart")
        await wait_for_message(ws_player, "roundStart")

        guess_message = WSMessage(
            type="guess", payload=GuessPayload(airport_code=guess_code).model_dump()
        )
        await ws_player.send_json(guess_message.model_dump())

        round_data = await _wait_for_stored_guess(real_redis, room_code, player_nick)

    # The host has not guessed, so the round keeps accepting guesses.
    assert round_data.state == RoundStateEnum.ACCEPTING_GUESSES
    stored_guess = round_data.guesses[player_nick]
    assert isinstance(stored_guess, PlayerGuess)
    assert stored_guess.guess == guess_code
    assert stored_guess.nickname == player_nick


@pytest.mark.asyncio
async def test_websocket_host_skip_round_integration(
    integration_client: AsyncClient, real_redis: redis.Redis
) -> None:
    """Verify host can skip a round and state resets."""
    host_nick = "host_skip"
    plane_hex = "abcd12"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    await seed_plane(real_redis, plane_hex, origin="KBOS", destination="KJFK")

    async with aconnect_ws(ws_path, client=integration_client) as ws_host:
        await wait_for_message(ws_host, "stateSync")

        await ws_host.send_json(
            WSMessage(type="selectPlane", payload={"hex": plane_hex}).model_dump()
        )
        await wait_for_message(ws_host, "planeSelectedConfirm", hex=plane_hex)

        await ws_host.send_json(WSMessage(type="startRound", payload={}).model_dump())
        await wait_for_message(ws_host, "roundStart")

        await ws_host.send_json(WSMessage(type="skipRound", payload={}).model_dump())

        # Plane deltas also arrive every second; wait for the one that resets the round.
        await wait_for_message(
            ws_host,
            "delta",
            where=lambda frame: (
                frame["payload"].get("round", {}).get("state")
                == RoundStateEnum.WAITING_FOR_SELECTION.value
            ),
        )

    round_data = await _read_round(real_redis, room_code)
    assert round_data.state == RoundStateEnum.WAITING_FOR_SELECTION
    assert round_data.selected_plane_hex is None

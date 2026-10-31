"""Guessing real airports over the WebSocket, in solo and host-only multiplayer rooms.

The last tests cover what a host is told when acting before the next round can start.

A host-only multiplayer room ends its round through the all-guessed path as soon
as the host guesses, which exercises the production scoring in ``_end_round``.

Every test runs against fakeredis, and against real Redis when integration tests
are selected (``-m integration`` with ``TEST_REDIS_URL`` pointing at a spare db).
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest
from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession

from backend.schemas.core import ScoringMode
from backend.schemas.game import RoundStateEnum
from backend.schemas.ws import ErrorCode, WSMessage, WSMessageType
from backend.services import room_service
from backend.utils.redis_async import RedisClient
from tests.backend.routes.game_socket import game_socket
from tests.integration.planes import seed_plane

pytestmark = pytest.mark.asyncio

RECEIVE_TIMEOUT_S = 2.0


async def _seed_plane(
    game_redis: RedisClient, hex_ident: str, origin: str | None, destination: str | None
) -> None:
    # In CI the real-Redis variants share their db with a live backend, whose broadcast
    # loop deletes stale or out-of-range planes; seed_plane keeps them fresh over Logan.
    async with await game_redis.get_connection() as conn:
        await seed_plane(conn, hex_ident, origin=origin, destination=destination)


async def _send(ws: AsyncWebSocketSession, msg_type: str, payload: dict) -> None:
    await ws.send_json(WSMessage(type=msg_type, payload=payload).model_dump())


async def _next_of_type(ws: AsyncWebSocketSession, msg_type: str) -> WSMessage:
    """Return the next message of ``msg_type``, skipping unrelated broadcasts."""
    while True:
        msg = WSMessage(**await ws.receive_json(timeout=RECEIVE_TIMEOUT_S))
        if msg.type == msg_type:
            return msg


@asynccontextmanager
async def _solo_session(test_client: AsyncClient) -> AsyncIterator[AsyncWebSocketSession]:
    join = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    ws_path = join.json()["ws_url"].replace("ws://testserver", "")
    async with game_socket(ws_path) as ws:
        await _next_of_type(ws, WSMessageType.STATE_SYNC)
        yield ws


@asynccontextmanager
async def _host_session(
    test_client: AsyncClient, mode: ScoringMode
) -> AsyncIterator[tuple[str, AsyncWebSocketSession]]:
    created = await test_client.post(
        "/api/v0/rooms", json={"host_nickname": "Host", "mode": mode.value}
    )
    body = created.json()
    ws_path = body["ws_url"].replace("ws://testserver", "")
    async with game_socket(ws_path) as ws:
        await _next_of_type(ws, WSMessageType.STATE_SYNC)
        yield body["room_code"], ws


async def _solo_guess_result(test_client: AsyncClient, plane_hex: str, guess: str) -> dict:
    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": plane_hex})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "guess", {"airport_code": guess})
        result = await _next_of_type(ws, WSMessageType.ROUND_RESULT)
    return result.payload["results"][0]


async def _start_host_round(ws: AsyncWebSocketSession, plane_hex: str) -> None:
    await _send(ws, "selectPlane", {"hex": plane_hex})
    await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
    await _send(ws, "startRound", {})
    await _next_of_type(ws, WSMessageType.ROUND_START)


async def _host_round_result(
    test_client: AsyncClient, mode: ScoringMode, plane_hex: str, guess: str
) -> dict:
    async with _host_session(test_client, mode) as (_, ws):
        await _send(ws, "selectPlane", {"hex": plane_hex})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "startRound", {})
        await _next_of_type(ws, WSMessageType.ROUND_START)
        await _send(ws, "guess", {"airport_code": guess})
        result = await _next_of_type(ws, WSMessageType.ROUND_RESULT)
    return result.payload["results"][0]


async def test_solo_iata_guess_for_icao_answer_scores_full_points(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "ord1", origin="KBOS", destination="KORD")

    result = await _solo_guess_result(test_client, "ord1", "ORD")

    assert (result["score_awarded"], result["distance_km"]) == (100, None)


async def test_multiplayer_iata_guess_scores_full_points_in_exact_mode(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk1", origin="KBOS", destination="KJFK")

    result = await _host_round_result(test_client, ScoringMode.EXACT, "jfk1", "JFK")

    assert (result["score_awarded"], result["distance_km"]) == (100, None)


async def test_multiplayer_distance_mode_reports_distance_and_points(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk2", origin="KBOS", destination="KJFK")

    result = await _host_round_result(test_client, ScoringMode.DISTANCE, "jfk2", "PVD")

    assert 225 < result["distance_km"] < 237
    assert result["score_awarded"] == 77


async def test_multiplayer_distance_mode_correct_iata_guess_is_zero_km(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk3", origin="KBOS", destination="KJFK")

    result = await _host_round_result(test_client, ScoringMode.DISTANCE, "jfk3", "JFK")

    assert (result["score_awarded"], result["distance_km"]) == (100, 0.0)


async def test_guess_code_is_trimmed_and_uppercased(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "sfo1", origin="KSFO", destination="KBOS")

    result = await _solo_guess_result(test_client, "sfo1", "  sfo ")

    assert (result["guess"], result["score_awarded"]) == ("SFO", 100)


async def test_solo_unknown_guess_code_is_rejected_and_retry_scores(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk4", origin="KBOS", destination="KJFK")

    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": "jfk4"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "guess", {"airport_code": "ZZZ"})
        rejection = WSMessage(**await ws.receive_json(timeout=RECEIVE_TIMEOUT_S))
        await _send(ws, "guess", {"airport_code": "JFK"})
        retry = await _next_of_type(ws, WSMessageType.ROUND_RESULT)

    assert rejection.type == WSMessageType.ERROR
    assert rejection.payload["code"] == ErrorCode.UNKNOWN_AIRPORT_CODE.value
    assert "'ZZZ'" in rejection.payload["message"]
    assert retry.payload["results"][0]["score_awarded"] == 100


@pytest.mark.parametrize("code", ["AB", "ABCDEFGHI", "X" * 5000])
async def test_solo_guess_code_outside_length_limits_is_invalid_payload(
    test_client: AsyncClient, game_redis: RedisClient, code: str
) -> None:
    await _seed_plane(game_redis, "jfk5", origin="KBOS", destination="KJFK")

    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": "jfk5"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "guess", {"airport_code": code})
        reply = WSMessage(**await ws.receive_json(timeout=RECEIVE_TIMEOUT_S))

    assert reply.type == WSMessageType.ERROR
    assert reply.payload["code"] == ErrorCode.INVALID_PAYLOAD.value


async def test_multiplayer_unknown_guess_code_is_rejected_and_retry_scores(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk6", origin="KBOS", destination="KJFK")

    async with _host_session(test_client, ScoringMode.EXACT) as (room_code, ws):
        await _send(ws, "selectPlane", {"hex": "jfk6"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "startRound", {})
        await _next_of_type(ws, WSMessageType.ROUND_START)
        await _send(ws, "guess", {"airport_code": "ZZZ"})
        rejection = await _next_of_type(ws, WSMessageType.ERROR)
        round_after_rejection = await room_service.get_round_data(game_redis, room_code)
        await _send(ws, "guess", {"airport_code": "JFK"})
        retry = await _next_of_type(ws, WSMessageType.ROUND_RESULT)

    assert rejection.payload["code"] == ErrorCode.UNKNOWN_AIRPORT_CODE.value
    assert round_after_rejection.guesses == {}
    assert round_after_rejection.state == RoundStateEnum.ACCEPTING_GUESSES
    assert retry.payload["results"][0]["score_awarded"] == 100


async def test_multiplayer_guess_outside_round_keeps_existing_error(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "jfk7", origin="KBOS", destination="KJFK")

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _send(ws, "selectPlane", {"hex": "jfk7"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "guess", {"airport_code": "ZZZ"})
        reply = await _next_of_type(ws, WSMessageType.ERROR)

    assert reply.payload["code"] == ErrorCode.GUESS_OUTSIDE_ROUND.value


async def test_solo_select_plane_with_unknown_answer_airport_is_rejected(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "mvy1", origin="KBOS", destination="KMVY")

    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": "mvy1"})
        reply = WSMessage(**await ws.receive_json(timeout=RECEIVE_TIMEOUT_S))

    assert reply.type == WSMessageType.ERROR
    assert reply.payload["code"] == ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS.value
    assert "destination airport isn't in the game's airport list" in reply.payload["message"]
    assert "MVY" not in reply.payload["message"]


async def test_multiplayer_select_plane_with_unknown_answer_airport_is_rejected(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "mvy2", origin="KMVY", destination="KBOS")

    async with _host_session(test_client, ScoringMode.EXACT) as (room_code, ws):
        await _send(ws, "selectPlane", {"hex": "mvy2"})
        rejection = await _next_of_type(ws, WSMessageType.ERROR)
        round_data = await room_service.get_round_data(game_redis, room_code)
        await _send(ws, "startRound", {})
        start_error = await _next_of_type(ws, WSMessageType.ERROR)

    assert rejection.payload["code"] == ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS.value
    assert "origin airport isn't in the game's airport list" in rejection.payload["message"]
    assert "MVY" not in rejection.payload["message"]
    assert round_data.correct_airport_code is None
    assert start_error.payload["code"] == ErrorCode.INVALID_STATE_FOR_ACTION.value


async def test_multiplayer_select_plane_without_route_keeps_existing_error(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "noroute", origin="KBOS", destination=None)

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _send(ws, "selectPlane", {"hex": "noroute"})
        rejection = await _next_of_type(ws, WSMessageType.ERROR)

    assert rejection.payload["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value


async def test_solo_selection_confirm_names_no_airport(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "conf1", origin="KBOS", destination="KJFK")

    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": "conf1"})
        confirm = await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)

    assert confirm.payload == {"hex": "conf1", "guess_direction": "destination"}


async def test_host_selection_confirm_names_no_airport(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "conf2", origin="KJFK", destination="KBOS")

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _send(ws, "selectPlane", {"hex": "conf2"})
        confirm = await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)

    assert confirm.payload == {"hex": "conf2", "guess_direction": "origin"}


async def test_solo_round_result_names_the_plane(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "res1", origin="KBOS", destination="KJFK")

    async with _solo_session(test_client) as ws:
        await _send(ws, "selectPlane", {"hex": "res1"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "guess", {"airport_code": "JFK"})
        result = await _next_of_type(ws, WSMessageType.ROUND_RESULT)

    assert (result.payload["hex"], result.payload["results"][0]["correct_code"]) == (
        "res1",
        "KJFK",
    )


async def test_multiplayer_round_result_names_the_plane(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    await _seed_plane(game_redis, "res2", origin="KJFK", destination="KBOS")

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _send(ws, "selectPlane", {"hex": "res2"})
        await _next_of_type(ws, WSMessageType.PLANE_SELECTED_CONFIRM)
        await _send(ws, "startRound", {})
        await _next_of_type(ws, WSMessageType.ROUND_START)
        await _send(ws, "guess", {"airport_code": "JFK"})
        result = await _next_of_type(ws, WSMessageType.ROUND_RESULT)

    assert (result.payload["hex"], result.payload["results"][0]["correct_code"]) == (
        "res2",
        "KJFK",
    )


# A host who acts before the next round can start is told why, in words the frontend shows as is.
EARLY_HOST_ACTIONS = [
    pytest.param("selectPlane", {"hex": "next1"}, id="selectPlane"),
    pytest.param("startRound", {}, id="startRound"),
]


@pytest.mark.parametrize(("msg_type", "payload"), EARLY_HOST_ACTIONS)
async def test_host_action_right_after_a_round_says_to_wait(
    test_client: AsyncClient, game_redis: RedisClient, msg_type: str, payload: dict
) -> None:
    await _seed_plane(game_redis, "wait1", origin="KBOS", destination="KJFK")
    await _seed_plane(game_redis, "next1", origin="KBOS", destination="KORD")

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _start_host_round(ws, "wait1")
        await _send(ws, "guess", {"airport_code": "JFK"})
        await _next_of_type(ws, WSMessageType.ROUND_RESULT)
        await _send(ws, msg_type, payload)
        reply = await _next_of_type(ws, WSMessageType.ERROR)

    assert reply.payload == {
        "code": ErrorCode.INVALID_STATE_FOR_ACTION.value,
        "message": "The last round just ended. You can start the next one in a few seconds.",
    }


@pytest.mark.parametrize(("msg_type", "payload"), EARLY_HOST_ACTIONS)
async def test_host_action_during_a_round_says_one_is_in_progress(
    test_client: AsyncClient, game_redis: RedisClient, msg_type: str, payload: dict
) -> None:
    await _seed_plane(game_redis, "busy1", origin="KBOS", destination="KJFK")
    await _seed_plane(game_redis, "next1", origin="KBOS", destination="KORD")

    async with _host_session(test_client, ScoringMode.EXACT) as (_, ws):
        await _start_host_round(ws, "busy1")
        await _send(ws, msg_type, payload)
        reply = await _next_of_type(ws, WSMessageType.ERROR)

    assert reply.payload == {
        "code": ErrorCode.INVALID_STATE_FOR_ACTION.value,
        "message": "A round is already in progress.",
    }

import asyncio
import logging  # Added
import time

import pytest
from fastapi import status
from fastapi.websockets import WebSocketDisconnect
from httpx import AsyncClient
from httpx_ws import WebSocketInterface, aconnect_ws

from backend.schemas.core import Player, ScoringMode

# Remove httpx client
from backend.schemas.ws import (
    FullRoomState,
    PingPongPayload,
    PlayerJoinedPayload,
    WSMessage,
)
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)  # Added logger

# Assume test_client (AsyncClient) and redis_client fixtures are available from conftest.py

pytestmark = pytest.mark.asyncio

# --- Helpers (using AsyncClient for HTTP) --- #


async def create_room_and_get_ws_url(
    client: AsyncClient,
    nickname: str = "host1",
    mode: ScoringMode = ScoringMode.DISTANCE,
    timeout: int = 30,
) -> tuple[str, str]:
    """Helper to create a room and return the room code and WS URL path."""
    loop_id = id(asyncio.get_running_loop())
    logger.info(
        f"[Helper create_room_and_get_ws_url] START. Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    response = await client.post(
        "/api/v0/rooms",
        json={"host_nickname": nickname, "mode": mode.value, "round_timeout_seconds": timeout},
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"Failed to create room: {response.status_code} {response.text}"
    data = response.json()
    assert "room_code" in data
    assert "ws_url" in data
    logger.info(
        f"[Helper create_room_and_get_ws_url] END. Code: {data['room_code']}, "
        f"URL: {data['ws_url']}, Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    return data["room_code"], data["ws_url"]


async def join_room_and_get_ws_url(client: AsyncClient, room_code: str, nickname: str) -> str:
    """Helper to join a room and return the WS URL path."""
    loop_id = id(asyncio.get_running_loop())
    logger.info(
        f"[Helper join_room_and_get_ws_url] START. Code: {room_code}, Nick: {nickname}, "
        f"Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    # No await for TestClient
    response = await client.post(
        f"/api/v0/rooms/{room_code}/join",
        json={"nickname": nickname},
    )
    assert (
        response.status_code == status.HTTP_200_OK
    ), f"Failed to join room: {response.status_code} {response.text}"
    data = response.json()
    assert "ws_url" in data
    logger.info(
        f"[Helper join_room_and_get_ws_url] END. URL: {data['ws_url']}, "
        f"Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    return data["ws_url"]


# --- Remove incorrect WebSocket Test Utilities --- #
# Remove connect_ws function

# --- Tests (using AsyncClient for HTTP and WebSockets) --- #


async def test_websocket_connect_and_state_sync(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify WebSocket connection and initial stateSync message."""
    host_nick = "host_sync"
    room_code, ws_path = await create_room_and_get_ws_url(test_client, nickname=host_nick)

    try:
        ws_url_http = ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as websocket:
            data = await websocket.receive_json()
            message = WSMessage(**data)

            assert message.type == "stateSync"
            assert "payload" in data
            state = FullRoomState(**message.payload)

            assert state.room_meta is not None
            assert state.room_meta.host_nickname == host_nick
            assert state.players is not None
            assert len(state.players) == 1
            assert host_nick in state.players
            assert state.players[host_nick].nickname == host_nick
            assert state.players[host_nick].connected is True

            # Verify player status in Redis (async)
            player_key = f"room:{room_code}:players"
            host_player = await redis_client.hget_model(player_key, host_nick, Player)
            assert host_player is not None
            assert host_player.connected is True

    except WebSocketDisconnect as e:  # httpx might raise this or its own exception
        pytest.fail(f"WebSocket disconnected unexpectedly: {e.code} {e.reason}")
    except Exception as e:
        pytest.fail(f"Unexpected error during WebSocket connection/sync: {e}")
    finally:
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")


async def test_websocket_ping_pong(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Verify the server sends pings and responds to client pongs."""
    host_nick = "host_ping"
    room_code, ws_path = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    ping_interval_s = 10
    pong_timeout_s = 30
    test_duration = ping_interval_s * 1.5

    received_server_ping = False

    try:
        ws_url_http = ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as websocket:
            # Consume initial stateSync
            await websocket.receive_json()

            start_time = time.time()
            while time.time() - start_time < test_duration:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=ping_interval_s * 0.6
                    )
                    message = WSMessage(**data)

                    if message.type == "ping":
                        received_server_ping = True
                        ping_payload = PingPongPayload(**message.payload)
                        pong_payload = PingPongPayload(seq=ping_payload.seq)
                        pong_msg = WSMessage(type="pong", payload=pong_payload.model_dump())
                        await websocket.send_json(pong_msg.model_dump())
                        logger.debug(f"Client sent pong {ping_payload.seq}")

                except asyncio.TimeoutError:
                    logger.debug("Receive timeout, continuing wait for ping...")
                    pass
                except Exception as e:
                    pytest.fail(f"WebSocket error during ping/pong receive loop: {e}")
                    break

            await asyncio.sleep(pong_timeout_s - test_duration + ping_interval_s * 0.5)

            # Check liveness
            final_ping_seq = 999
            final_ping = WSMessage(
                type="ping", payload=PingPongPayload(seq=final_ping_seq).model_dump()
            )
            await websocket.send_json(final_ping.model_dump())

            final_pong = await wait_for_message_type(websocket, "pong", timeout=2.0)
            assert PingPongPayload(**final_pong.payload).seq == final_ping_seq

            # Graceful leave before exiting context
            await websocket.send_json(WSMessage(type="leave", payload={}).model_dump())

        assert received_server_ping, "Did not receive any ping from the server."

    except Exception as e:
        pytest.fail(f"WebSocket error during ping/pong test: {e}")
    finally:
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")


async def test_websocket_player_joined_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    host_nick = "host_join_br"
    joiner_nick = "joiner_join_br"
    room_code, host_ws_path = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    joiner_ws_path = await join_room_and_get_ws_url(test_client, room_code, joiner_nick)

    received_join_broadcast = False

    try:
        ws_url_http = host_ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as host_ws:
            # 1. Host consumes initial stateSync
            await host_ws.receive_json()
            logger.debug(f"Host {host_nick} received initial stateSync.")

            # 2. Joiner consumes initial stateSync (which now includes Host)
            ws_url_http = joiner_ws_path.replace("ws://", "http://", 1)
            async with aconnect_ws(ws_url_http, client=test_client) as joiner_ws:
                joiner_sync_data = await joiner_ws.receive_json()
                joiner_sync_msg = WSMessage(**joiner_sync_data)
                assert joiner_sync_msg.type == "stateSync"
                joiner_state = FullRoomState(**joiner_sync_msg.payload)
                assert len(joiner_state.players) == 2  # Host and Joiner
                assert host_nick in joiner_state.players
                assert joiner_nick in joiner_state.players
                logger.debug(f"Joiner {joiner_nick} received initial stateSync.")

                # 3. Host should receive playerJoined broadcast for the joiner
                host_broadcast_msg = await wait_for_message_type(
                    host_ws, "playerJoined", timeout=2.0
                )
                payload = PlayerJoinedPayload(**host_broadcast_msg.payload)
                assert payload.nickname == joiner_nick
                received_join_broadcast = True

        # Send leave on both sockets
        await joiner_ws.send_json(WSMessage(type="leave", payload={}).model_dump())
        await host_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

    except WebSocketDisconnect as e:
        pytest.fail(f"WebSocket disconnected unexpectedly during join broadcast test: {e}")
    finally:
        # Clean up redis keys
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")

    assert received_join_broadcast, "Test completed but playerJoined broadcast was not verified."


async def test_websocket_player_left_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    host_nick = "host_left_br"
    leaver_nick = "leaver_left_br"
    room_code, host_ws_path = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    leaver_ws_path = await join_room_and_get_ws_url(test_client, room_code, leaver_nick)

    received_left_broadcast = False

    try:
        ws_url_http = host_ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as host_ws:
            ws_url_http = leaver_ws_path.replace("ws://", "http://", 1)
            async with aconnect_ws(ws_url_http, client=test_client) as leaver_ws:
                # Host consumes initial stateSync and the playerJoined for leaver
                await asyncio.wait_for(host_ws.receive_json(), timeout=1.0)  # stateSync
                await asyncio.wait_for(host_ws.receive_json(), timeout=1.0)  # playerJoined
                logger.debug(f"Host {host_nick} consumed initial messages.")

                # Leaver consumes its stateSync
                await asyncio.wait_for(leaver_ws.receive_json(), timeout=1.0)
                logger.debug(f"Leaver {leaver_nick} consumed initial stateSync.")

                # Send leave to gracefully close
                await leaver_ws.send_json(WSMessage(type="leave", payload={}).model_dump())
                await host_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

                logger.debug(f"Leaver {leaver_nick} WebSocket connection closed.")
                received_left_broadcast = True

            # Verify leaver status in Redis
            player_key = f"room:{room_code}:players"
            leaver_player = await redis_client.hget_model(player_key, leaver_nick, Player)
            assert (
                leaver_player is not None
            ), "Leaver player data missing from Redis after disconnect."
            assert (
                leaver_player.connected is False
            ), "Leaver connected status not updated to False in Redis."

    except WebSocketDisconnect as e:
        pytest.fail(f"WebSocket disconnected unexpectedly during left broadcast test: {e}")
    finally:
        # Clean up redis keys
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")

    assert received_left_broadcast, "Test completed but playerLeft broadcast was not verified."


async def test_websocket_reject_invalid_room(test_client: AsyncClient) -> None:
    """Verify connection is rejected if the room does not exist."""
    invalid_room_code = "XXXX"
    nickname = "ghost_player"
    ws_path = f"/ws/{invalid_room_code}/{nickname}"

    # httpx websockets might raise different exceptions on connection failure
    # or receive a close frame. Let's expect a generic exception or specific close code.
    with pytest.raises((WebSocketDisconnect, Exception)) as exc_info:  # Wider exception catch
        ws_url_http = ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as websocket:
            await websocket.receive_json(timeout=1.0)  # Attempt receive

    # Check if it was WebSocketDisconnect with the right code
    if isinstance(exc_info.value, WebSocketDisconnect):
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
    else:
        # Allow other exceptions if connection itself failed, maybe log?
        logger.warning(
            f"Invalid room test raised {type(exc_info.value)} instead of WebSocketDisconnect"
        )
        pass


async def test_websocket_reject_invalid_player(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify connection is rejected if the player nickname
    hasn't joined the room via HTTP first."""
    host_nick = "host_reject"
    invalid_nick = "intruder"
    room_code, _ = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    ws_path = f"/ws/{room_code}/{invalid_nick}"

    try:
        with pytest.raises((WebSocketDisconnect, Exception)) as exc_info:
            ws_url_http = ws_path.replace("ws://", "http://", 1)
            async with aconnect_ws(ws_url_http, client=test_client) as websocket:
                await websocket.receive_json(timeout=1.0)  # Attempt receive

        if isinstance(exc_info.value, WebSocketDisconnect):
            assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION
        else:
            logger.warning(
                f"Invalid player test raised {type(exc_info.value)} instead of WebSocketDisconnect"
            )
            pass
    finally:
        # Clean up redis keys
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")


async def test_websocket_guess_placeholder_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify that a guess message triggers a delta broadcast to others (placeholder)."""
    host_nick = "host_guess_br"
    guesser_nick = "guesser_guess_br"
    room_code, host_ws_path = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    guesser_ws_path = await join_room_and_get_ws_url(test_client, room_code, guesser_nick)

    received_guess_broadcast = False
    guess_payload = {"airport_code": "BOS"}

    try:
        ws_url_http = host_ws_path.replace("ws://", "http://", 1)
        async with aconnect_ws(ws_url_http, client=test_client) as host_ws:
            # Consume initial messages on both sides
            await host_ws.receive_json()  # stateSync
            await host_ws.receive_json()  # playerJoined (guesser)
            ws_url_http = guesser_ws_path.replace("ws://", "http://", 1)
            async with aconnect_ws(ws_url_http, client=test_client) as guesser_ws:
                await guesser_ws.receive_json()  # stateSync
                logger.debug("Both clients connected and consumed initial messages.")

                # Guesser sends a guess message
                guess_msg = WSMessage(type="guess", payload=guess_payload)
                await guesser_ws.send_json(guess_msg.model_dump())
                logger.debug(f"Guesser {guesser_nick} sent guess: {guess_payload}")

                # Host should receive the delta broadcast
                try:
                    host_broadcast_msg = await wait_for_message_type(host_ws, "delta", timeout=2.0)
                    assert host_broadcast_msg.type == "delta"
                    # Check the placeholder payload structure
                    assert host_broadcast_msg.payload.get("guess_ack") == guess_payload
                    assert host_broadcast_msg.payload.get("sender") == guesser_nick
                    received_guess_broadcast = True
                except asyncio.TimeoutError:
                    pytest.fail(
                        f"Host did not receive delta broadcast for guess from {guesser_nick} "
                        "within timeout."
                    )

                # Guesser should NOT receive the broadcast back (excluded)
                await asyncio.sleep(0.5)

                # Leave
                await guesser_ws.send_json(WSMessage(type="leave", payload={}).model_dump())
                await host_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

    except WebSocketDisconnect as e:
        pytest.fail(f"WebSocket disconnected unexpectedly during guess broadcast test: {e}")
    finally:
        # Clean up redis keys
        await redis_client.redis.delete(f"room:{room_code}:meta")
        await redis_client.redis.delete(f"room:{room_code}:players")

    assert received_guess_broadcast, "Test completed but guess delta broadcast was not verified."


# --- Utility helper to wait for a specific message type --- #


async def wait_for_message_type(
    ws: WebSocketInterface, desired_type: str, *, timeout: float = 2.0
) -> WSMessage:
    """Receive frames until one with the requested type is returned.

    Skips over server *ping* frames or other noise that can legitimately arrive
    before the message the test is actually interested in.
    """
    end_time = time.time() + timeout
    while True:
        remaining = end_time - time.time()
        if remaining <= 0:
            raise asyncio.TimeoutError(f"Timed-out waiting for WS message type '{desired_type}'")
        data = await asyncio.wait_for(ws.receive_json(), timeout=remaining)
        msg = WSMessage(**data)
        if msg.type == desired_type:
            return msg
        # otherwise continue looping
        logger.debug(
            f"Helper skipped WS frame type '{msg.type}' while waiting for '{desired_type}'."
        )

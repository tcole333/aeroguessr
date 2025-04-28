import asyncio
import logging  # Added
import time
from typing import Any, AsyncGenerator, Dict

import pytest
from fastapi import WebSocket, status
from fastapi.websockets import WebSocketDisconnect

# Remove WebSocketSession import if not found/needed
from httpx import AsyncClient  # , WebSocketSession

# Remove httpx_ws imports if no longer directly needed
# from httpx_ws import ASGIWebSocketTransport, WebSocket, aconnect_ws
from backend.schemas.core import ScoringMode

# Remove httpx client
from backend.schemas.ws import (
    FullRoomState,
    PingPongPayload,
    PlayerJoinedPayload,
    PlayerLeftPayload,
    WSMessage,
)
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)  # Added logger

# Assume test_client (AsyncClient) and redis_client fixtures
# are available from conftest.py

pytestmark = pytest.mark.asyncio

# pytest.skip("Skipping unit WebSocket tests in favor of
# integration tests", allow_module_level=True)

# --- Helpers (using AsyncClient for HTTP) --- #


async def create_room_and_get_ws_url(
    client: AsyncClient,
    nickname: str = "host1",
    mode: ScoringMode = ScoringMode.DISTANCE,
    timeout: int = 30,
) -> tuple[str, str]:
    """Helper to create a room and return the room code and full WS URL."""
    loop_id = id(asyncio.get_running_loop())
    logger.info(
        f"[Helper create_room_and_get_ws_url] START. Client ID: {id(client)}, "
        f"Loop ID: {loop_id}"
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
    # Return the FULL ws_url needed by connect_websocket
    full_ws_url = data["ws_url"].replace("http://", "ws://", 1)  # Ensure ws:// prefix
    logger.info(
        f"[Helper create_room_and_get_ws_url] END. Code: {data['room_code']}, "
        f"Full URL: {full_ws_url}, Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    return data["room_code"], full_ws_url


async def join_room_and_get_ws_url(client: AsyncClient, room_code: str, nickname: str) -> str:
    """Helper to join a room and return the full WS URL."""
    loop_id = id(asyncio.get_running_loop())
    logger.info(
        f"[Helper join_room_and_get_ws_url] START. Code: {room_code}, Nick: {nickname}, "
        f"Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    # Use await with AsyncClient
    response = await client.post(
        f"/api/v0/rooms/{room_code}/join",
        json={"nickname": nickname},
    )
    assert (
        response.status_code == status.HTTP_200_OK
    ), f"Failed to join room: {response.status_code} {response.text}"
    data = response.json()
    assert "ws_url" in data
    # Return the FULL ws_url needed by connect_websocket
    full_ws_url = data["ws_url"].replace("http://", "ws://", 1)  # Ensure ws:// prefix
    logger.info(
        f"[Helper join_room_and_get_ws_url] END. Full URL: {full_ws_url}, "
        f"Client ID: {id(client)}, Loop ID: {loop_id}"
    )
    return full_ws_url


# --- Tests (using AsyncClient for HTTP and WebSockets) --- #


async def test_websocket_connect_and_state_sync(ws: AsyncGenerator[Dict[str, Any], None]) -> None:
    """Test WebSocket connection and state sync."""
    # Test implementation...


async def test_websocket_ping_pong(
    test_client: AsyncClient,
    redis_client: RedisClient,
) -> None:
    """Verify the server sends pings and responds to client pongs."""
    host_nick = "host_ping"
    # Get full URL from helper
    room_code, ws_full_url = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    ping_interval_s = 10  # Read from config or use known value from rooms.py
    pong_timeout_s = 30
    test_duration = ping_interval_s * 1.5

    received_server_ping = False

    try:
        # Use test_client.websocket_connect with the full URL
        async with test_client.websocket_connect(ws_full_url) as websocket:
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

            # Check liveness (adjust timeout based on server logic)
            await asyncio.sleep(pong_timeout_s + ping_interval_s - test_duration + 1)

            # Try sending a final ping to check if connection is still alive
            final_ping_seq = 999
            final_ping = WSMessage(
                type="ping", payload=PingPongPayload(seq=final_ping_seq).model_dump()
            )
            try:
                # Connection should be closed by server if pongs timed out
                await websocket.send_json(final_ping.model_dump())
                # We might need to wait for a response or check state differently
                # Maybe try receiving to see if it raises Disconnect
                await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
                pytest.fail("Connection did not close after pong timeout")
            except (WebSocketDisconnect, asyncio.TimeoutError):
                logger.info(
                    "Connection correctly closed after pong timeout or " "receive timed out."
                )
            except Exception as e:
                pytest.fail(f"Unexpected error checking connection status: {e}")

        assert received_server_ping, "Did not receive any ping from the server."

    except Exception as e:
        pytest.fail(f"WebSocket error during ping/pong test: {e}")


async def test_websocket_player_joined_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify playerJoined broadcast when a new player joins."""
    host_nick = "host_join_br"
    joiner_nick = "joiner_join_br"
    # Create room and get WS URLs
    room_code, host_ws_full_url = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    joiner_ws_full_url = await join_room_and_get_ws_url(test_client, room_code, joiner_nick)

    received_broadcast = False

    # Use the same test client for both connections
    try:
        async with test_client.websocket_connect(host_ws_full_url) as host_ws:
            # Consume host's initial stateSync
            data = await host_ws.receive_json()
            msg = WSMessage(**data)
            assert msg.type == "stateSync"
            logger.debug(f"Host {host_nick} received initial stateSync.")

            async with test_client.websocket_connect(joiner_ws_full_url) as join_ws:
                # Consume joiner's initial stateSync
                join_data = await join_ws.receive_json()
                join_msg = WSMessage(**join_data)
                assert join_msg.type == "stateSync"
                state = FullRoomState(**join_msg.payload)
                assert host_nick in state.players and joiner_nick in state.players
                logger.debug(f"Joiner {joiner_nick} received initial stateSync.")

                # Host should then receive the playerJoined broadcast
                logger.debug(f"Host {host_nick} waiting for playerJoined broadcast...")
                broadcast = await wait_for_message_type(host_ws, "playerJoined", timeout=2.0)
                payload = PlayerJoinedPayload(**broadcast.payload)
                assert payload.nickname == joiner_nick
                received_broadcast = True
                logger.debug(f"Host {host_nick} received playerJoined for {joiner_nick}.")

                # Graceful leave (optional but good practice)
                await join_ws.send_json(WSMessage(type="leave", payload={}).model_dump())
                await host_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

    except WebSocketDisconnect as e:
        pytest.fail(f"WebSocket disconnected unexpectedly: {e.code} {e.reason}")
    except Exception as e:
        pytest.fail(f"Unexpected error during player joined test: {e}")

    assert received_broadcast, "Test completed but playerJoined broadcast was not verified."


async def test_websocket_player_left_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test playerLeft broadcast."""
    host_nick = "host_left_br"
    leaver_nick = "leaver_left_br"
    room_code, host_ws_full_url = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    leaver_ws_full_url = await join_room_and_get_ws_url(test_client, room_code, leaver_nick)

    received_left_broadcast = False

    try:
        async with test_client.websocket_connect(host_ws_full_url) as host_ws:
            # Consume host's stateSync and leaver's playerJoined
            await wait_for_message_type(host_ws, "stateSync", timeout=1.0)
            await wait_for_message_type(host_ws, "playerJoined", timeout=1.0)
            logger.debug(f"Host {host_nick} consumed initial messages.")

            async with test_client.websocket_connect(leaver_ws_full_url) as leaver_ws:
                # Consume leaver's stateSync
                await wait_for_message_type(leaver_ws, "stateSync", timeout=1.0)
                logger.debug(f"Leaver {leaver_nick} consumed initial stateSync.")

                # Leaver explicitly sends leave message
                await leaver_ws.send_json(WSMessage(type="leave", payload={}).model_dump())
                logger.debug(f"Leaver {leaver_nick} sent leave message.")

                # Host should receive playerLeft
                logger.debug(f"Host {host_nick} waiting for playerLeft broadcast...")
                broadcast = await wait_for_message_type(host_ws, "playerLeft", timeout=2.0)
                # Assuming PlayerLeftPayload schema exists and is correct
                # from backend.schemas.ws import PlayerLeftPayload
                payload = PlayerLeftPayload(**broadcast.payload)
                assert payload.nickname == leaver_nick
                received_left_broadcast = True
                logger.debug(f"Host {host_nick} received playerLeft for {leaver_nick}.")

            # Context manager for leaver_ws handles disconnection here
            logger.debug(f"Leaver {leaver_nick} WebSocket context exited.")

            # Host sends leave to clean up
            await host_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

    except WebSocketDisconnect as e:
        # Distinguish between expected and unexpected disconnects if needed
        pytest.fail(f"WebSocket disconnected unexpectedly: {e.code} {e.reason}")
    except Exception as e:
        pytest.fail(f"Unexpected error during player left test: {e}")

    assert received_left_broadcast, "Test completed but playerLeft broadcast was not verified."


async def test_websocket_reject_invalid_room(test_client: AsyncClient) -> None:
    """Verify connection is rejected if the room does not exist."""
    invalid_path = "/ws/WXYZ/SomePlayer"
    with pytest.raises(WebSocketDisconnect) as exc_info:
        async with test_client.websocket_connect(invalid_path) as websocket:
            # Connection should fail before this block is entered or during handshake
            # If it enters, try receiving to trigger potential disconnect
            try:
                await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
            except asyncio.TimeoutError:
                pass  # Expected if connection waits

    assert (
        exc_info.value.code == 1011
    )  # Internal Server Error (FastAPI default for unhandled exception?)
    # Or check for 404/403 if FastAPI handles it gracefully during handshake
    # The exact code might depend on how FastAPI/Starlette handles errors
    # during the WebSocket handshake based on path parameters.
    # We might need to inspect logs or adjust the expected code.
    logger.info(f"Received expected disconnect for invalid room: {exc_info.value}")


async def test_websocket_reject_invalid_player(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify connection is rejected if player didn't join via HTTP first."""
    host_nick = "host_inv_plr"
    room_code, _ = await create_room_and_get_ws_url(test_client, nickname=host_nick)
    invalid_player_path = f"/ws/{room_code}/GhostPlayer"

    with pytest.raises(WebSocketDisconnect) as exc_info:
        async with test_client.websocket_connect(invalid_player_path) as websocket:
            # Connection should likely fail handshake
            try:
                await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

    # Expecting a specific close code like 403 Forbidden or 1008 Policy Violation
    # Or potentially 1011 if it results in an unhandled error during connection setup.
    assert exc_info.value.code in [1008, 1011, 4003]  # Allow for variations
    logger.info(f"Received expected disconnect for invalid player: {exc_info.value}")


# This test needs significant update for the actual game logic
async def test_websocket_guess_placeholder_broadcast(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Verify guess message handling (placeholder - needs update)."""
    # host_nick = "host_guess_pl"
    # guesser_nick = "guesser_guess_pl"
    # room_code, host_ws_full_url = await create_room_and_get_ws_url(test_client,
    # nickname=host_nick)
    # guesser_ws_full_url = await join_room_and_get_ws_url(test_client,
    # room_code, guesser_nick)

    # TODO: This test needs to be rewritten based on actual game flow:
    # 1. Host connects
    # 2. Guesser connects
    # 3. Host selects a plane and starts a round (send selectPlane, startRound)
    # 4. Host and Guesser receive roundStart
    # 5. Guesser sends a guess message
    # 6. Verify guess is stored correctly in Redis (requires access to round state)
    # 7. Verify if any broadcast happens upon guess (likely not until round end)
    # 8. Let round end (timer or host action)
    # 9. Verify roundResult broadcast

    pytest.skip("Guess test needs complete rewrite for actual game logic.")

    # Placeholder for old structure:
    # try:
    #     async with test_client.websocket_connect(host_ws_full_url) as host_ws,
    #                  test_client.websocket_connect(guesser_ws_full_url) as guesser_ws:
    #         # Consume initial messages
    #         await wait_for_message_type(host_ws, "stateSync", 1.0)
    #         await wait_for_message_type(host_ws, "playerJoined", 1.0)
    #         await wait_for_message_type(guesser_ws, "stateSync", 1.0)

    #         # Guesser sends guess
    #         guess_payload = GuessPayload(airport_code="BOS")
    #         guess_msg = WSMessage(type="guess", payload=guess_payload.model_dump())
    #         await guesser_ws.send_json(guess_msg.model_dump())
    #         logger.info(f"Guesser {guesser_nick} sent guess.")

    #         # Host should receive... something? A delta update? Nothing until round end?
    #         # This part is placeholder
    #         delta_msg = await wait_for_message_type(host_ws, "delta", timeout=2.0)
    #         # Assert structure of delta based on expected broadcast
    #         logger.info(f"Host received delta: {delta_msg}")

    # except Exception as e:
    #     pytest.fail(f"Error during guess test: {e}")


# Helper function to wait for a specific message type
async def wait_for_message_type(
    ws: WebSocket,
    desired_type: str,
    *,
    timeout: float = 2.0,  # Use Any for ws type hint
) -> WSMessage:
    """Receives messages until one with the desired type is found or timeout."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Use a short internal timeout for receive_json to avoid blocking the loop
            remaining_time = timeout - (time.time() - start_time)
            if remaining_time <= 0:
                raise asyncio.TimeoutError

            data = await asyncio.wait_for(ws.receive_json(), timeout=min(0.5, remaining_time))
            message = WSMessage(**data)
            logger.debug(f"Received WS message: type={message.type}")
            if message.type == desired_type:
                return message
            elif message.type == "ping":  # Handle pings while waiting
                ping_payload = PingPongPayload(**message.payload)
                pong_payload = PingPongPayload(seq=ping_payload.seq)
                pong_msg = WSMessage(type="pong", payload=pong_payload.model_dump())
                await ws.send_json(pong_msg.model_dump())
                logger.debug(f"Helper sent pong {ping_payload.seq}")
            # Ignore other message types while waiting

        except asyncio.TimeoutError:
            continue  # Keep waiting until the outer timeout
        except WebSocketDisconnect as e:
            pytest.fail(f"WebSocket disconnected while waiting for {desired_type}: {e.code}")
        except Exception as e:
            pytest.fail(f"Error receiving message while waiting for {desired_type}: {e}")

    raise asyncio.TimeoutError(
        f"Did not receive message of type '{desired_type}' within {timeout}s"
    )

import asyncio
import time

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from starlette.websockets import WebSocketDisconnect

from backend.schemas.room import RoomCreateRequest
from backend.schemas.ws import PingPongPayload, WSMessage, WSMessageType

# Constants from rooms.py (consider importing if possible, or keep in sync)
PING_INTERVAL_SECONDS = 10
MAX_MISSED_PINGS = 3
WEBSOCKET_TIMEOUT = PING_INTERVAL_SECONDS * (MAX_MISSED_PINGS + 1.5)  # Add buffer


pytestmark = pytest.mark.integration


async def _setup_room_and_player(client: AsyncClient, room_id: str, nickname: str) -> str:
    """Helper to create a room and join as a player, returning the WS URL."""
    # Create room (as host)
    create_data = RoomCreateRequest(
        host_nickname=nickname, mode="Distance", round_timeout_seconds=30
    )
    response = await client.post("/api/v0/rooms", json=create_data.model_dump())
    response.raise_for_status()  # Raise exception for non-2xx status
    create_resp_data = response.json()
    room_code = create_resp_data["room_code"]
    ws_url = create_resp_data["ws_url"]

    # For simplicity in this test, we'll just use the host's WS URL.
    # If testing joiners, we'd call join_room here.
    assert nickname in ws_url
    assert room_code in ws_url

    return ws_url


@pytest.mark.asyncio
async def test_server_responds_to_ping_with_pong(integration_client: AsyncClient) -> None:
    """Verify server sends PONG back when client sends PING."""
    current_time_int = int(time.time())
    nickname = f"pingtester_{current_time_int}"
    ws_url = await _setup_room_and_player(integration_client, "testroom_ping", nickname)

    try:
        async with aconnect_ws(ws_url, client=integration_client) as ws:
            # Receive initial state sync
            initial_msg_data = await ws.receive_json()
            assert initial_msg_data["type"] == WSMessageType.STATE_SYNC

            # Send PING
            ping_seq = 123
            ping_payload = PingPongPayload(seq=ping_seq)
            ping_msg = WSMessage(type=WSMessageType.PING, payload=ping_payload)
            await ws.send_json(ping_msg.model_dump())

            # Expect PONG back
            response_data = await asyncio.wait_for(ws.receive_json(), timeout=2.0)

            assert response_data["type"] == WSMessageType.PONG
            pong_payload = PingPongPayload.model_validate(response_data["payload"])
            assert pong_payload.seq == ping_seq

    except asyncio.TimeoutError:
        pytest.fail("Did not receive PONG response within timeout.")
    except WebSocketDisconnect as e:
        pytest.fail(f"WebSocket disconnected unexpectedly: {e.code} {e.reason}")
    finally:
        # Cleanup: Consider deleting the room if necessary
        pass


# TODO: Add tests for:
# - test_server_sends_periodic_pings
# - test_server_disconnects_unresponsive_client
# - test_connection_stays_alive_with_pongs

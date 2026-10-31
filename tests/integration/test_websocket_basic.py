"""
Basic WebSocket integration tests migrated from unit tests in
`tests/backend/routes/test_websocket.py`.
These now run against the real server and Redis stack.
"""

import pytest
from fastapi import status
from httpx import AsyncClient
from httpx_ws import WebSocketUpgradeError, aconnect_ws
from starlette.websockets import WebSocketDisconnect

from backend.schemas.core import ScoringMode
from backend.schemas.ws import PingPongPayload, WSMessage

from .ws_helpers import wait_for_message

pytestmark = pytest.mark.integration

# The server pings every PING_INTERVAL_SECONDS (10s, backend/routes/rooms.py).
SERVER_PING_TIMEOUT_SECONDS = 12.0


@pytest.mark.asyncio
async def test_websocket_ping_pong_integration(integration_client: AsyncClient) -> None:
    """Verify server sends ping and accepts pong responses."""
    host_nick = "host_ping"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    ws_path = f"/api/v0/rooms/ws/{room_code}/{host_nick}"

    async with aconnect_ws(
        ws_path, client=integration_client, keepalive_ping_interval_seconds=None
    ) as ws:
        await wait_for_message(ws, "stateSync")

        ping = await wait_for_message(ws, "ping", timeout=SERVER_PING_TIMEOUT_SECONDS)
        ping_payload = PingPongPayload(**ping["payload"])
        await ws.send_json(WSMessage(type="pong", payload=ping_payload.model_dump()).model_dump())

        # The server keeps the connection open after a valid pong: a client ping still
        # gets its pong back.
        await ws.send_json(WSMessage(type="ping", payload={"seq": 7}).model_dump())
        await wait_for_message(ws, "pong", seq=7)


@pytest.mark.asyncio
async def test_websocket_player_left_broadcast_integration(
    integration_client: AsyncClient,
) -> None:
    """Verify playerLeft broadcast when a player leaves."""
    host_nick = "host_left"
    leaver_nick = "leaver_left"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    resp2 = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": leaver_nick}
    )
    assert resp2.status_code == status.HTTP_200_OK

    ws_host = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_leaver = f"/api/v0/rooms/ws/{room_code}/{leaver_nick}"

    async with aconnect_ws(
        ws_host, client=integration_client, keepalive_ping_interval_seconds=None
    ) as host_ws:
        await wait_for_message(host_ws, "stateSync")

        async with aconnect_ws(
            ws_leaver, client=integration_client, keepalive_ping_interval_seconds=None
        ) as leaver_ws:
            await wait_for_message(leaver_ws, "stateSync")
            await wait_for_message(host_ws, "playerJoined", nickname=leaver_nick)

            await leaver_ws.send_json(WSMessage(type="leave", payload={}).model_dump())

            await wait_for_message(host_ws, "playerLeft", nickname=leaver_nick)


@pytest.mark.asyncio
async def test_websocket_reject_invalid_room_integration(
    integration_client: AsyncClient,
) -> None:
    """Verify connection is rejected for non-existent room."""
    invalid_ws = "/api/v0/rooms/ws/ZZZZ/ghost"
    with pytest.raises((WebSocketDisconnect, WebSocketUpgradeError)):
        async with aconnect_ws(invalid_ws, client=integration_client):
            pass


@pytest.mark.asyncio
async def test_websocket_reject_invalid_player_integration(
    integration_client: AsyncClient,
) -> None:
    """Verify connection is rejected if player didn't join first."""
    host_nick = "host_inv"
    resp = await integration_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": host_nick,
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 10,
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED
    room_code = resp.json()["room_code"]
    invalid_ws = f"/api/v0/rooms/ws/{room_code}/ghost_player"
    with pytest.raises((WebSocketDisconnect, WebSocketUpgradeError)):
        async with aconnect_ws(invalid_ws, client=integration_client):
            pass

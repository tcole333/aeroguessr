"""
Basic WebSocket integration tests migrated from unit tests in
`tests/backend/routes/test_websocket.py`.
These now run against the real server and Redis stack.
"""

import logging
import asyncio

import httpx_ws._api
import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws
from starlette.websockets import WebSocketDisconnect

from backend.schemas.core import ScoringMode
from backend.schemas.ws import PingPongPayload, PlayerJoinedPayload, PlayerLeftPayload, WSMessage

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


# Disable background keepalive pings to avoid protocol errors on closing
# ruff: noqa
async def _noop_background(self, *args, **kwargs) -> None:
    return


httpx_ws._api.AsyncWebSocketSession._background_keepalive = _noop_background


@pytest.mark.asyncio
async def test_websocket_ping_pong_integration(
    integration_client: AsyncClient,
    integration_redis: redis.Redis,
) -> None:
    """Verify server sends ping and accepts pong responses."""
    host_nick = "host_ping"
    # Create room
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

    received_ping = False
    pong_sent = False
    async with aconnect_ws(
        ws_path, client=integration_client, keepalive_ping_interval_seconds=None
    ) as ws:
        # Consume initial stateSync
        data = await ws.receive_json()
        msg = WSMessage(**data)
        assert msg.type == "stateSync"

        # Await one server ping, allowing for other messages and a timeout
        start_time = asyncio.get_event_loop().time()
        timeout_duration = 12  # seconds (WEBSOCKET_PING_INTERVAL is 10s)
        while asyncio.get_event_loop().time() - start_time < timeout_duration:
            try:
                # Use a shorter timeout for individual receive calls
                data = await asyncio.wait_for(ws.receive_json(), timeout=1.0)
            except asyncio.TimeoutError:
                # No message received in 1s, continue waiting for ping
                logger.debug("No message in 1s, continuing to wait for PING")
                continue

            msg = WSMessage(**data)
            logger.debug(f"Received message type: {msg.type}")
            if msg.type == "ping":
                received_ping = True
                ping_payload = PingPongPayload(**msg.payload)
                pong_msg = WSMessage(type="pong", payload=ping_payload.model_dump())
                await ws.send_json(pong_msg.model_dump())
                pong_sent = True
                logger.info(f"Received PING (seq={ping_payload.seq}), sent PONG.")
                break  # Exit loop once ping is received and pong is sent
            elif msg.type == "delta":
                logger.debug("Received DELTA message, ignoring and continuing.")
            # Add other message types to ignore if necessary
            # else:
            #     logger.warning(f"Received unexpected message type: {msg.type}")

    assert received_ping, "Did not receive any ping from server within timeout."
    assert pong_sent, "Did not send PONG to server."


@pytest.mark.asyncio
async def test_websocket_player_left_broadcast_integration(
    integration_client: AsyncClient,
    integration_redis: redis.Redis,
) -> None:
    """Verify playerLeft broadcast when a player leaves."""
    host_nick = "host_left"
    leaver_nick = "leaver_left"
    # Create room
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
    # Player joins
    resp2 = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": leaver_nick}
    )
    assert resp2.status_code == status.HTTP_200_OK

    ws_host = f"/api/v0/rooms/ws/{room_code}/{host_nick}"
    ws_leaver = f"/api/v0/rooms/ws/{room_code}/{leaver_nick}"

    async with aconnect_ws(
        ws_host, client=integration_client, keepalive_ping_interval_seconds=None
    ) as host_ws:
        # Initial stateSync for host
        raw = await host_ws.receive_json()
        msg = WSMessage(**raw)
        assert msg.type == "stateSync"

        # Connect leaver to trigger join event
        async with aconnect_ws(
            ws_leaver, client=integration_client, keepalive_ping_interval_seconds=None
        ) as leaver_ws:
            # Leaver receives its stateSync
            leav_raw = await leaver_ws.receive_json()
            leav_msg = WSMessage(**leav_raw)
            assert leav_msg.type == "stateSync"

            # Host should receive playerJoined broadcast
            while True:
                data = await host_ws.receive_json()
                join_msg = WSMessage(**data)
                if join_msg.type == "ping":
                    # respond to server ping to keep connection alive
                    ping_payload = PingPongPayload(**join_msg.payload)
                    pong = WSMessage(type="pong", payload=ping_payload.model_dump())
                    await host_ws.send_json(pong.model_dump())
                    continue
                if join_msg.type == "playerJoined":
                    assert PlayerJoinedPayload(**join_msg.payload).nickname == leaver_nick
                    break

            # Leaver leaves
            leave_msg = WSMessage(type="leave", payload={})
            await leaver_ws.send_json(leave_msg.model_dump())

            # Host should receive playerLeft broadcast
            while True:
                data = await host_ws.receive_json()
                leave_brd = WSMessage(**data)
                if leave_brd.type == "ping":
                    ping_payload = PingPongPayload(**leave_brd.payload)
                    pong = WSMessage(type="pong", payload=ping_payload.model_dump())
                    await host_ws.send_json(pong.model_dump())
                    continue
                if leave_brd.type == "playerLeft":
                    payload = PlayerLeftPayload(**leave_brd.payload)
                    assert payload.nickname == leaver_nick
                    break


@pytest.mark.asyncio
async def test_websocket_reject_invalid_room_integration(
    integration_client: AsyncClient,
) -> None:
    """Verify connection is rejected for non-existent room."""
    invalid_ws = "/api/v0/rooms/ws/ZZZZ/ghost"
    # handshake refusal surfaces as WebSocketUpgradeError in httpx_ws
    from httpx_ws._exceptions import WebSocketUpgradeError

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
    # handshake refusal surfaces as WebSocketUpgradeError in httpx_ws
    from httpx_ws._exceptions import WebSocketUpgradeError

    with pytest.raises((WebSocketDisconnect, WebSocketUpgradeError)):
        async with aconnect_ws(invalid_ws, client=integration_client):
            pass

"""
Integration tests for WebSocket endpoints against a real backend+Redis stack.
Requires `docker-compose -f infra/docker-compose.test.yml up -d` before running.
Mark tests with @pytest.mark.integration.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.schemas.core import ScoringMode
from backend.schemas.ws import FullRoomState, PlayerJoinedPayload, WSMessage

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_websocket_connect_and_state_sync_integration(http_server: TestClient) -> None:
    """Verify WebSocket stateSync comes through on a real server."""
    async with AsyncClient(base_url=http_server) as client:
        # Create a room
        payload = {
            "host_nickname": "int_host",
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 15,
        }
        resp = await client.post("/api/v0/rooms", json=payload)
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        ws_url = data["ws_url"].replace("http://", "ws://", 1)

        # Connect via WebSocket
        async with aconnect_ws(ws_url, client=client) as ws:
            msg_raw = await ws.receive_json()
            msg = WSMessage(**msg_raw)
            assert msg.type == "stateSync"
            state = FullRoomState(**msg.payload)
            # Host should be alone and connected
            assert state.room_meta.host_nickname == "int_host"
            assert len(state.players) == 1


@pytest.mark.asyncio
async def test_websocket_player_join_broadcast_integration(http_server: TestClient) -> None:
    """Verify playerJoined broadcast on a real server."""
    async with AsyncClient(base_url=http_server) as client:
        # Host creates room
        resp = await client.post(
            "/api/v0/rooms",
            json={
                "host_nickname": "host2",
                "mode": ScoringMode.EXACT.value,
                "round_timeout_seconds": 10,
            },
        )
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        ws_host = data["ws_url"].replace("http://", "ws://", 1)

        # Joiner joins via HTTP
        room_code = data["room_code"]
        resp2 = await client.post(f"/api/v0/rooms/{room_code}/join", json={"nickname": "join2"})
        assert resp2.status_code == status.HTTP_200_OK
        ws_join = resp2.json()["ws_url"].replace("http://", "ws://", 1)

        # Connect host and consume stateSync
        async with aconnect_ws(ws_host, client=client) as ws_h:
            await ws_h.receive_json()
            # Connect joiner to trigger broadcast
            async with aconnect_ws(ws_join, client=client) as ws_j:
                await ws_j.receive_json()
            # Host should receive playerJoined
            br = await ws_h.receive_json()
            msg = WSMessage(**br)
            assert msg.type == "playerJoined"
            payload = PlayerJoinedPayload(**msg.payload)
            assert payload.nickname == "join2"

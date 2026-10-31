"""Integration tests for host transfer broadcasts."""

from typing import NamedTuple

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis
from httpx_ws import aconnect_ws

from backend.schemas.core import RoomMeta

from .ws_helpers import Expected, wait_for_message, wait_for_messages

pytestmark = pytest.mark.integration

HOST = "HostPlayer"
PLAYER = "NormalPlayer"


class HostAndPlayer(NamedTuple):
    room_code: str
    host_ws_url: str
    player_ws_url: str


@pytest_asyncio.fixture
async def host_and_player(integration_client: httpx.AsyncClient) -> HostAndPlayer:
    """Create a room hosted by HOST that PLAYER has joined over REST."""
    host_response = await integration_client.post(
        "/api/v0/rooms",
        json={"host_nickname": HOST, "mode": "Exact", "round_timeout_seconds": 30},
    )
    assert host_response.status_code == 201
    host_data = host_response.json()
    room_code = host_data["room_code"]

    player_response = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": PLAYER}
    )
    assert player_response.status_code == 200
    return HostAndPlayer(room_code, host_data["ws_url"], player_response.json()["ws_url"])


async def _read_meta(redis_conn: redis.Redis, room_code: str) -> RoomMeta:
    meta_json = await redis_conn.get(f"room:{room_code}:meta")
    assert meta_json is not None, f"room:{room_code}:meta is missing"
    return RoomMeta.model_validate_json(meta_json)


@pytest.mark.asyncio
async def test_host_transfer_broadcasts_to_all_clients(
    integration_client: httpx.AsyncClient, host_and_player: HostAndPlayer
) -> None:
    """Test that host transfer is broadcast to all connected clients."""
    async with aconnect_ws(host_and_player.host_ws_url, integration_client) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        async with aconnect_ws(host_and_player.player_ws_url, integration_client) as player_ws:
            await wait_for_message(player_ws, "stateSync")
            await wait_for_message(host_ws, "playerJoined", nickname=PLAYER)

            await host_ws.send_json({"type": "transferHost", "payload": {"to_nickname": PLAYER}})

            await wait_for_message(host_ws, "newHost", nickname=PLAYER)
            await wait_for_message(player_ws, "newHost", nickname=PLAYER)


@pytest.mark.asyncio
async def test_host_leaves_room_transfers_host(
    integration_client: httpx.AsyncClient, host_and_player: HostAndPlayer
) -> None:
    """Test that host leaving automatically transfers host role."""
    async with aconnect_ws(host_and_player.host_ws_url, integration_client) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        async with aconnect_ws(host_and_player.player_ws_url, integration_client) as player_ws:
            await wait_for_message(player_ws, "stateSync")
            await wait_for_message(host_ws, "playerJoined", nickname=PLAYER)

            await host_ws.send_json({"type": "leave", "payload": {}})

            # Both broadcasts follow the host's departure, so collect them in one wait.
            await wait_for_messages(
                player_ws,
                Expected("playerLeft", {"nickname": HOST}),
                Expected("newHost", {"nickname": PLAYER}),
            )


@pytest.mark.asyncio
async def test_multiple_players_host_transfer_updates(
    integration_client: httpx.AsyncClient, host_and_player: HostAndPlayer
) -> None:
    """Test host transfer updates with multiple players in room."""
    player2_response = await integration_client.post(
        f"/api/v0/rooms/{host_and_player.room_code}/join", json={"nickname": "Player2"}
    )
    assert player2_response.status_code == 200
    player2_ws_url = player2_response.json()["ws_url"]

    async with aconnect_ws(host_and_player.host_ws_url, integration_client) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        async with aconnect_ws(host_and_player.player_ws_url, integration_client) as player1_ws:
            await wait_for_message(player1_ws, "stateSync")
            await wait_for_message(host_ws, "playerJoined", nickname=PLAYER)
            async with aconnect_ws(player2_ws_url, integration_client) as player2_ws:
                await wait_for_message(player2_ws, "stateSync")
                await wait_for_message(host_ws, "playerJoined", nickname="Player2")
                await wait_for_message(player1_ws, "playerJoined", nickname="Player2")

                await host_ws.send_json(
                    {"type": "transferHost", "payload": {"to_nickname": "Player2"}}
                )

                for ws in (host_ws, player1_ws, player2_ws):
                    await wait_for_message(ws, "newHost", nickname="Player2")


@pytest.mark.asyncio
async def test_host_state_persists_after_transfer(
    integration_client: httpx.AsyncClient,
    host_and_player: HostAndPlayer,
    real_redis: redis.Redis,
) -> None:
    """Test that host state persists in Redis after transfer."""
    async with aconnect_ws(host_and_player.host_ws_url, integration_client) as host_ws:
        await wait_for_message(host_ws, "stateSync")
        async with aconnect_ws(host_and_player.player_ws_url, integration_client) as player_ws:
            await wait_for_message(player_ws, "stateSync")
            await wait_for_message(host_ws, "playerJoined", nickname=PLAYER)

            await host_ws.send_json({"type": "transferHost", "payload": {"to_nickname": PLAYER}})
            await wait_for_message(player_ws, "newHost", nickname=PLAYER)

            meta = await _read_meta(real_redis, host_and_player.room_code)

    assert meta.host_nickname == PLAYER

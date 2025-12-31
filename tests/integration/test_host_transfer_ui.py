"""Integration tests for host transfer UI updates."""

import asyncio
from typing import Any, AsyncGenerator, Dict, Tuple

import httpx
import pytest
from httpx_ws import aconnect_ws


@pytest.fixture
async def host_and_player(
    integration_client: httpx.AsyncClient,
) -> AsyncGenerator[Tuple[str, str, str, str], None]:
    """Create a room with host and a joined player."""
    # Create room as host
    host_response = await integration_client.post(
        "/api/v0/rooms",
        json={"host_nickname": "HostPlayer", "mode": "Exact", "round_timeout_seconds": 30},
    )
    assert host_response.status_code == 201
    host_data = host_response.json()
    room_code = host_data["room_code"]
    host_ws_url = host_data["ws_url"]

    # Join room as player
    player_response = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join",
        json={"nickname": "NormalPlayer"},
    )
    assert player_response.status_code == 200
    player_data = player_response.json()
    player_ws_url = player_data["ws_url"]

    yield room_code, host_ws_url, player_ws_url, "HostPlayer"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_host_transfer_broadcasts_to_all_clients(
    integration_client: httpx.AsyncClient, host_and_player: Tuple[str, str, str, str]
):
    """Test that host transfer is broadcast to all connected clients."""
    room_code, host_ws_url, player_ws_url, initial_host = host_and_player

    # Connect both clients
    async with aconnect_ws(host_ws_url, integration_client) as host_ws:
        async with aconnect_ws(player_ws_url, integration_client) as player_ws:
            # Clear initial messages
            await host_ws.receive_json()  # stateSync
            await player_ws.receive_json()  # stateSync
            await host_ws.receive_json()  # playerJoined for player

            # Host transfers to player
            transfer_msg: Dict[str, Any] = {
                "type": "transferHost",
                "payload": {"to_nickname": "NormalPlayer"},
            }
            await host_ws.send_json(transfer_msg)

            # Both clients should receive newHost message
            host_received = False
            player_received = False

            # Check host receives newHost
            msg_data = await host_ws.receive_json()
            if msg_data.get("type") == "newHost":
                assert msg_data["payload"]["nickname"] == "NormalPlayer"
                host_received = True

            # Check player receives newHost
            msg_data = await player_ws.receive_json()
            if msg_data.get("type") == "newHost":
                assert msg_data["payload"]["nickname"] == "NormalPlayer"
                player_received = True

            assert host_received and player_received


@pytest.mark.integration
@pytest.mark.asyncio
async def test_host_leaves_room_transfers_host(
    integration_client: httpx.AsyncClient, host_and_player: Tuple[str, str, str, str]
):
    """Test that host leaving automatically transfers host role."""
    room_code, host_ws_url, player_ws_url, initial_host = host_and_player

    # Connect both clients
    async with aconnect_ws(host_ws_url, integration_client) as host_ws:
        async with aconnect_ws(player_ws_url, integration_client) as player_ws:
            # Clear initial messages
            await host_ws.receive_json()  # stateSync
            await player_ws.receive_json()  # stateSync
            await host_ws.receive_json()  # playerJoined

            # Host leaves room
            leave_msg: Dict[str, Any] = {"type": "leave", "payload": {}}
            await host_ws.send_json(leave_msg)

            # Player should receive both playerLeft and newHost messages
            player_left_received = False
            new_host_received = False

            # Receive messages (order may vary)
            for _ in range(2):
                msg_data = await player_ws.receive_json()

                if msg_data.get("type") == "playerLeft":
                    assert msg_data["payload"]["nickname"] == "HostPlayer"
                    player_left_received = True
                elif msg_data.get("type") == "newHost":
                    assert msg_data["payload"]["nickname"] == "NormalPlayer"
                    new_host_received = True

            assert player_left_received and new_host_received


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_players_host_transfer_updates(
    integration_client: httpx.AsyncClient, host_and_player: Tuple[str, str, str, str]
):
    """Test host transfer updates with multiple players in room."""
    room_code, host_ws_url, player1_ws_url, initial_host = host_and_player

    # Add a third player
    player2_response = await integration_client.post(
        f"/api/v0/rooms/{room_code}/join",
        json={"nickname": "Player2"},
    )
    assert player2_response.status_code == 200
    player2_data = player2_response.json()
    player2_ws_url = player2_data["ws_url"]

    # Connect all clients
    async with aconnect_ws(host_ws_url, integration_client) as host_ws:
        async with aconnect_ws(player1_ws_url, integration_client) as player1_ws:
            async with aconnect_ws(player2_ws_url, integration_client) as player2_ws:
                # Clear initial messages
                await asyncio.gather(
                    host_ws.receive_json(),  # stateSync
                    player1_ws.receive_json(),  # stateSync
                    player2_ws.receive_json(),  # stateSync
                )

                # Clear playerJoined messages
                await host_ws.receive_json()  # playerJoined for player1
                await host_ws.receive_json()  # playerJoined for player2
                await player1_ws.receive_json()  # playerJoined for player2

                # Host transfers to Player2
                transfer_msg: Dict[str, Any] = {
                    "type": "transferHost",
                    "payload": {"to_nickname": "Player2"},
                }
                await host_ws.send_json(transfer_msg)

                # All three clients should receive newHost message
                received_count = 0

                # Check all clients receive the message
                for ws in [host_ws, player1_ws, player2_ws]:
                    msg_data = await ws.receive_json()
                    if msg_data.get("type") == "newHost":
                        assert msg_data["payload"]["nickname"] == "Player2"
                        received_count += 1

                assert received_count == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_host_state_persists_after_transfer(
    integration_client: httpx.AsyncClient, host_and_player: Tuple[str, str, str, str]
):
    """Test that host state persists in Redis after transfer."""
    room_code, host_ws_url, player_ws_url, initial_host = host_and_player

    # Connect both clients
    async with aconnect_ws(host_ws_url, integration_client) as host_ws:
        async with aconnect_ws(player_ws_url, integration_client) as player_ws:
            # Clear initial messages
            await host_ws.receive_json()  # stateSync
            await player_ws.receive_json()  # stateSync
            await host_ws.receive_json()  # playerJoined

            # Transfer host
            transfer_msg: Dict[str, Any] = {
                "type": "transferHost",
                "payload": {"to_nickname": "NormalPlayer"},
            }
            await host_ws.send_json(transfer_msg)

            # Wait for newHost messages
            await host_ws.receive_json()
            await player_ws.receive_json()

            # Verify room state via API
            room_response = await integration_client.get(f"/api/v0/rooms/{room_code}")
            assert room_response.status_code == 200
            room_data = room_response.json()
            assert room_data["host_nickname"] == "NormalPlayer"

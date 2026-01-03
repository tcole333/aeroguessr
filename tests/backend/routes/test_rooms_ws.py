import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.ingest.main import PlaneState
from backend.schemas.ws import WSMessage, WSMessageType
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def test_solo_ws_flow(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Test solo mode WebSocket flow with default (Exact) scoring."""
    join_resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    data = join_resp.json()
    ws_path = data["ws_url"].replace("ws://testserver", "")

    plane = PlaneState(
        hex_ident="abcd",
        lat=0,
        lon=0,
        alt=0,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=0,
        origin="KBOS",
        destination="KJFK",
    )
    await redis_client.set_json("plane:abcd", plane)

    async with aconnect_ws(ws_path, client=test_client, keepalive_ping_interval_seconds=None) as ws:
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        select_msg = WSMessage(type="selectPlane", payload={"hex": "abcd"})
        await ws.send_json(select_msg.model_dump())
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM

        guess_msg = WSMessage(type="guess", payload={"airport_code": "KJFK"})
        await ws.send_json(guess_msg.model_dump())
        result = WSMessage(**await ws.receive_json())
        assert result.type == WSMessageType.ROUND_RESULT

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())


async def test_solo_ws_distance_mode_flow(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test solo mode WebSocket flow with Distance scoring.

    Regression test for issue #111 - Distance mode freezes after guess submission.
    This test verifies that the Distance mode round completes properly and returns
    the correct scoring format including distance_km in the results.
    """
    # Create a Distance mode room by creating a standard room first, then joining solo
    # For solo mode, we need to set up the room meta with Distance mode
    from backend.schemas.core import RoomMeta, ScoringMode

    # First join solo to get the room code
    join_resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "SoloDist"})
    assert join_resp.status_code == 200
    data = join_resp.json()
    room_code = data["room_code"]
    ws_path = data["ws_url"].replace("ws://testserver", "")

    # Update the room meta to use Distance scoring mode
    meta_key = f"room:{room_code}:meta"
    room_meta = RoomMeta(
        mode=ScoringMode.DISTANCE,
        round_timeout_seconds=30,
        host_nickname="SoloDist",
        is_solo=True,
    )
    await redis_client.set_json(meta_key, room_meta)

    # Set up a plane with known airports for distance calculation
    # Use IATA codes (BOS, JFK) which are available in the fallback airport data
    plane = PlaneState(
        hex_ident="dist1",
        lat=42.3656,  # BOS coordinates
        lon=-71.0096,
        alt=35000,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=0,
        origin="BOS",  # IATA code
        destination="JFK",  # IATA code - ~300km from BOS
    )
    await redis_client.set_json("plane:dist1", plane)

    async with aconnect_ws(ws_path, client=test_client, keepalive_ping_interval_seconds=None) as ws:
        # Receive initial state sync
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        # Select the plane
        select_msg = WSMessage(type="selectPlane", payload={"hex": "dist1"})
        await ws.send_json(select_msg.model_dump())
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM
        assert confirm.payload["hex"] == "dist1"
        assert confirm.payload["guess_direction"] == "destination"

        # Submit a guess with a different airport to get partial distance score
        # Providence (PVD) is ~70km from JFK (both in fallback data)
        guess_msg = WSMessage(type="guess", payload={"airport_code": "PVD"})
        await ws.send_json(guess_msg.model_dump())
        result = WSMessage(**await ws.receive_json())

        # Verify round completes (this was failing before the fix)
        assert result.type == WSMessageType.ROUND_RESULT
        assert "results" in result.payload
        assert len(result.payload["results"]) == 1

        # Verify the result contains distance scoring information
        player_result = result.payload["results"][0]
        assert player_result["nickname"] == "SoloDist"
        assert player_result["correct_code"] == "JFK"
        assert player_result["guess"] == "PVD"
        # Distance mode should include distance_km in results
        assert "distance_km" in player_result
        # Score should be partial (not 0 or 100) since PVD is not JFK but relatively close
        assert 0 <= player_result["score_awarded"] <= 100

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())


async def test_solo_ws_distance_mode_exact_guess(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test Distance mode with an exact correct guess.

    Verifies that an exact match in Distance mode returns 100 points and distance_km of 0.

    Note: Uses IATA codes (JFK, BOS) which are available in the fallback airport data.
    """
    from backend.schemas.core import RoomMeta, ScoringMode

    join_resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "SoloExact"})
    data = join_resp.json()
    room_code = data["room_code"]
    ws_path = data["ws_url"].replace("ws://testserver", "")

    # Set Distance mode
    meta_key = f"room:{room_code}:meta"
    room_meta = RoomMeta(
        mode=ScoringMode.DISTANCE,
        round_timeout_seconds=30,
        host_nickname="SoloExact",
        is_solo=True,
    )
    await redis_client.set_json(meta_key, room_meta)

    # Use IATA codes (JFK, BOS) which are in the fallback airport data
    plane = PlaneState(
        hex_ident="exact1",
        lat=42.3656,
        lon=-71.0096,
        alt=35000,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=0,
        origin="BOS",  # IATA code
        destination="JFK",  # IATA code (available in fallback data)
    )
    await redis_client.set_json("plane:exact1", plane)

    async with aconnect_ws(ws_path, client=test_client, keepalive_ping_interval_seconds=None) as ws:
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        select_msg = WSMessage(type="selectPlane", payload={"hex": "exact1"})
        await ws.send_json(select_msg.model_dump())
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM

        # Guess the exact correct answer using IATA code
        guess_msg = WSMessage(type="guess", payload={"airport_code": "JFK"})
        await ws.send_json(guess_msg.model_dump())
        result = WSMessage(**await ws.receive_json())

        assert result.type == WSMessageType.ROUND_RESULT
        player_result = result.payload["results"][0]
        assert player_result["score_awarded"] == 100
        assert player_result["distance_km"] == 0.0

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())


async def test_solo_ws_ping_pong(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Test that solo mode correctly handles ping/pong heartbeat messages.

    Regression test for issue #128 - Solo mode disconnects during gameplay.
    The root cause was that the solo loop did not handle PING messages from
    the frontend client, causing error responses instead of proper PONG replies.
    """
    join_resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "SoloPing"})
    data = join_resp.json()
    ws_path = data["ws_url"].replace("ws://testserver", "")

    plane = PlaneState(
        hex_ident="ping1",
        lat=0,
        lon=0,
        alt=0,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=0,
        origin="KBOS",
        destination="KJFK",
    )
    await redis_client.set_json("plane:ping1", plane)

    async with aconnect_ws(ws_path, client=test_client, keepalive_ping_interval_seconds=None) as ws:
        # Receive initial state sync
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        # Send a PING message (as frontend does every 10 seconds)
        ping_msg = WSMessage(type="ping", payload={"seq": 12345})
        await ws.send_json(ping_msg.model_dump())

        # Should receive a PONG response (not an error)
        response = WSMessage(**await ws.receive_json())
        assert response.type == WSMessageType.PONG
        assert response.payload["seq"] == 12345

        # Now proceed with normal game flow to ensure ping handling doesn't break gameplay
        select_msg = WSMessage(type="selectPlane", payload={"hex": "ping1"})
        await ws.send_json(select_msg.model_dump())
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM

        # Send another ping during gameplay
        ping_msg2 = WSMessage(type="ping", payload={"seq": 12346})
        await ws.send_json(ping_msg2.model_dump())
        response2 = WSMessage(**await ws.receive_json())
        assert response2.type == WSMessageType.PONG
        assert response2.payload["seq"] == 12346

        # Complete with a guess
        guess_msg = WSMessage(type="guess", payload={"airport_code": "KJFK"})
        await ws.send_json(guess_msg.model_dump())
        result = WSMessage(**await ws.receive_json())
        assert result.type == WSMessageType.ROUND_RESULT

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())

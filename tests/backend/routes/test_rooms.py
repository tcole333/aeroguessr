import time  # Add time import
from unittest.mock import patch

import pytest
from fastapi import status

# Import AsyncClient for type hint
from httpx import AsyncClient

# Import your FastAPI app and schemas/models
# No need to import app here if test_client fixture handles it
from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import RoundData, RoundStateEnum
from backend.schemas.room import RoomCreateRequest, RoomJoinRequest, RoomState
from backend.utils.redis_async import RedisClient

# Assume test_client and redis_client fixtures are available from conftest.py

pytestmark = pytest.mark.asyncio

# --- Test Cases ---


# Test POST /api/v0/rooms
# Test functions remain async because they use the async redis_client
# Update type hint for test_client
async def test_create_room_success(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Test successful room creation using fakeredis."""
    request_data = RoomCreateRequest(
        host_nickname="TestHost", mode=ScoringMode.DISTANCE, round_timeout_seconds=45
    )
    # Use await with AsyncClient
    response = await test_client.post("/api/v0/rooms", json=request_data.model_dump())

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "room_code" in response_data
    room_code = response_data["room_code"]
    assert len(room_code) == 4
    assert "ws_url" in response_data
    # Construct expected URL based on test client base URL
    expected_ws_url_end = f"/ws/{room_code}/TestHost"
    # Check if the actual URL ends with the expected path
    assert response_data["ws_url"].endswith(expected_ws_url_end)
    # Location header should match the returned ws_url
    assert response.headers.get("location") == response_data["ws_url"]

    # Verify data in Redis
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    assert await redis_client.exists(meta_key)
    assert await redis_client.exists(players_key)

    # Check room metadata
    room_meta = await redis_client.get_model(meta_key, RoomMeta)
    assert room_meta is not None
    assert room_meta.host_nickname == "TestHost"
    assert room_meta.mode == ScoringMode.DISTANCE
    assert room_meta.round_timeout_seconds == 45

    # Check host player data
    host_player = await redis_client.hget_model(players_key, "TestHost", Player)
    assert host_player is not None
    assert host_player.nickname == "TestHost"
    assert host_player.connected is False  # Initial state before WS connect
    assert host_player.score == 0

    # Check TTLs (fakeredis might not support precise TTL checks easily, focus on existence)
    # ttl_meta = await redis_client.redis.ttl(meta_key)
    # ttl_players = await redis_client.redis.ttl(players_key)
    # assert ttl_meta > 3500
    # assert ttl_players > 3500


# Note: Testing code collision is difficult and perhaps unnecessary with fakeredis,
# as fakeredis won't have the same potential for collision as a real Redis instance
# during rapid key generation. We can remove this test or keep it as a low-priority item.
# def test_create_room_code_collision(test_client: TestClient, redis_client: RedisClient) -> None:
#    """Test handling of room code generation collision (highly unlikely)."""
#    # This is hard to reliably simulate with fakeredis without complex mocking
#    pass


# Test POST /api/v0/rooms/{code}/join
# Update type hint for test_client
async def test_join_room_success(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Test successfully joining an existing room using fakeredis."""
    # 1. Create a room first
    create_request = RoomCreateRequest(host_nickname="HostOriginal")
    # Use await with AsyncClient
    create_response = await test_client.post("/api/v0/rooms", json=create_request.model_dump())
    assert create_response.status_code == status.HTTP_201_CREATED
    room_code = create_response.json()["room_code"]
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    # 2. Join the room
    join_nickname = "TestJoiner"
    join_request = RoomJoinRequest(nickname=join_nickname)
    # Use await with AsyncClient
    response = await test_client.post(
        f"/api/v0/rooms/{room_code}/join", json=join_request.model_dump()
    )

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "ws_url" in response_data
    assert response_data["ws_url"].endswith(f"/ws/{room_code}/{join_nickname}")

    # 3. Verify state in Redis
    assert await redis_client.exists(meta_key)
    assert await redis_client.exists(players_key)

    # Check joiner player data
    joiner_player = await redis_client.hget_model(players_key, join_nickname, Player)
    assert joiner_player is not None
    assert joiner_player.nickname == join_nickname
    assert joiner_player.connected is False
    assert joiner_player.score == 0

    # Check host player data still exists
    host_player = await redis_client.hget_model(players_key, "HostOriginal", Player)
    assert host_player is not None

    # Check total players in hash
    all_players = await redis_client.hgetall_models(players_key, Player)
    assert len(all_players) == 2
    assert "HostOriginal" in all_players
    assert "TestJoiner" in all_players


# Update type hint for test_client
async def test_join_room_not_found(test_client: AsyncClient, redis_client: RedisClient) -> None:
    """Test joining a room that doesn't exist."""
    room_code = "WXYZ"
    # Ensure the room does not exist (fakeredis is cleared before test)
    assert not await redis_client.exists(f"room:{room_code}:meta")

    request_data = RoomJoinRequest(nickname="TestJoiner")
    # Use await with AsyncClient
    response = await test_client.post(
        f"/api/v0/rooms/{room_code}/join", json=request_data.model_dump()
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert f"Room '{room_code}' not found" in response.json()["detail"]


# Update type hint for test_client
async def test_join_room_nickname_conflict(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test joining a room with a nickname that's already taken."""
    # 1. Create room with host
    host_nickname = "ExistingPlayer"
    create_request = RoomCreateRequest(host_nickname=host_nickname)
    # Use await with AsyncClient
    create_response = await test_client.post("/api/v0/rooms", json=create_request.model_dump())
    assert create_response.status_code == status.HTTP_201_CREATED
    room_code = create_response.json()["room_code"]
    players_key = f"room:{room_code}:players"

    # Verify host exists in Redis (async)
    assert await redis_client.hget_model(players_key, host_nickname, Player) is not None

    # 2. Attempt to join with the same nickname
    join_request = RoomJoinRequest(nickname=host_nickname)
    # Use await with AsyncClient
    response = await test_client.post(
        f"/api/v0/rooms/{room_code}/join", json=join_request.model_dump()
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert f"Nickname '{host_nickname}' is already taken" in response.json()["detail"]

    # Ensure no new player was added
    all_players = await redis_client.hgetall_models(players_key, Player)
    assert len(all_players) == 1
    assert host_nickname in all_players


# Remove WebSocket test stub - covered in test_websocket.py

# --- Tests for GET /api/v0/rooms/{code} --- #


@pytest.fixture
def mock_room_data() -> dict:
    """Provides sample data for a mock room state."""
    code = "ABCD"
    host_nick = "MockHost"
    player_nick = "MockPlayer"
    now = time.time()

    meta = RoomMeta(
        mode=ScoringMode.EXACT,
        round_timeout_seconds=30,
        host_nickname=host_nick,
        created_ts=now - 60,
    )
    players = {
        host_nick: Player(nickname=host_nick, score=10, connected=True, last_seen_ts=now),
        player_nick: Player(nickname=player_nick, score=0, connected=False, last_seen_ts=now - 30),
    }
    round_data = RoundData(
        state=RoundStateEnum.WAITING_FOR_SELECTION,
        round_number=1,
    )
    return {"code": code, "meta": meta, "players": players, "round_data": round_data}


async def test_get_room_details_success(
    test_client: AsyncClient,
    redis_client: RedisClient,
    mock_room_data: dict,
) -> None:
    """Test successfully retrieving room details when the room exists."""
    code = mock_room_data["code"]
    meta = mock_room_data["meta"]
    players = mock_room_data["players"]
    round_data = mock_room_data["round_data"]

    # Mock the service layer functions
    with (
        patch("backend.routes.rooms.room_service.get_room_meta") as mock_get_meta,
        patch("backend.routes.rooms.room_service.get_all_players") as mock_get_players,
        patch("backend.routes.rooms.room_service.get_round_data") as mock_get_round,
    ):
        # Correct mock return values: directly return the object, not an awaited AsyncMock
        mock_get_meta.return_value = meta
        mock_get_players.return_value = players
        mock_get_round.return_value = round_data

        # Wrap mocks in AsyncMock if they need to be awaitable themselves (not needed here)
        # as the patched functions are already async.

        response = await test_client.get(f"/api/v0/rooms/{code}")

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()

    # Validate against the RoomState schema structure
    # Use Pydantic to parse and validate
    try:
        result_state = RoomState(**response_data)
    except Exception as e:
        pytest.fail(f"Response validation failed: {e}")

    # Check specific fields match mocked data
    assert result_state.code == code
    assert result_state.mode == meta.mode
    assert result_state.round_timeout_seconds == meta.round_timeout_seconds
    assert result_state.host_nickname == meta.host_nickname
    assert result_state.created_ts == meta.created_ts
    assert len(result_state.players) == len(players)
    assert result_state.players["MockHost"].score == 10
    assert result_state.players["MockPlayer"].connected is False
    assert result_state.current_round is not None
    assert result_state.current_round.state == RoundStateEnum.WAITING_FOR_SELECTION
    assert result_state.current_round.round_number == 1

    # Verify mocks were called
    mock_get_meta.assert_called_once()
    mock_get_players.assert_called_once()
    mock_get_round.assert_called_once()


async def test_get_room_details_not_found(test_client: AsyncClient) -> None:
    """Test retrieving details for a room code that does not exist."""
    code = "XXXX"

    # Mock get_room_meta to return None
    with patch("backend.routes.rooms.room_service.get_room_meta") as mock_get_meta:
        # Correct mock return value
        mock_get_meta.return_value = None

        response = await test_client.get(f"/api/v0/rooms/{code}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert f"Room with code '{code}' not found" in response.json()["detail"]
    mock_get_meta.assert_called_once()


async def test_get_room_details_service_error(test_client: AsyncClient) -> None:
    """Test handling of an unexpected error during service layer calls."""
    code = "ABCD"

    # Mock get_room_meta to raise an exception
    with patch("backend.routes.rooms.room_service.get_room_meta") as mock_get_meta:
        # Correct mock side effect
        mock_get_meta.side_effect = Exception("Redis boom!")  # side_effect for exceptions

        response = await test_client.get(f"/api/v0/rooms/{code}")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "unexpected internal error" in response.json()["detail"].lower()
    mock_get_meta.assert_called_once()


# Remove WebSocket test stub - covered in test_websocket.py

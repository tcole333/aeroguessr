from typing import Generator
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

# Import your FastAPI app and schemas/models
from backend.app import app
from backend.routes.rooms import get_redis_client  # To override dependency
from backend.schemas.core import Player, ScoringMode
from backend.schemas.room import RoomCreateRequest, RoomJoinRequest
from backend.utils.redis_async import RedisClient

# Use FastAPI's TestClient
client = TestClient(app)

# --- Mocks and Fixtures ---


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Fixture to provide a mock RedisClient instance."""
    mock = AsyncMock(spec=RedisClient)
    mock.exists = AsyncMock(return_value=False)  # Default: key doesn't exist
    mock.set_json = AsyncMock()
    mock.expire = AsyncMock()
    mock.hset_model = AsyncMock()
    mock.hget_model = AsyncMock(return_value=None)  # Default: field doesn't exist
    mock.hgetall_models = AsyncMock(return_value={})  # Default: empty hash
    return mock


@pytest.fixture(autouse=True)
def override_redis_dependency(mock_redis: AsyncMock) -> Generator[None, None, None]:
    """Fixture to automatically override the RedisClient dependency for all tests in this module."""

    async def get_mock_redis_client() -> RedisClient:
        return mock_redis

    app.dependency_overrides[get_redis_client] = get_mock_redis_client
    yield
    # Clean up override after test
    app.dependency_overrides = {}


# --- Test Cases ---


# Test POST /api/v0/rooms
def test_create_room_success(mock_redis: AsyncMock) -> None:
    """Test successful room creation."""
    request_data = RoomCreateRequest(
        host_nickname="TestHost", mode=ScoringMode.DISTANCE, round_timeout_seconds=45
    )
    response = client.post("/api/v0/rooms", json=request_data.model_dump())

    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert "room_code" in response_data
    assert len(response_data["room_code"]) == 4
    assert "ws_url" in response_data
    assert response_data["ws_url"].endswith(f"/ws/{response_data['room_code']}/TestHost")
    assert response.headers.get("location") == response_data["ws_url"]

    # Verify Redis calls
    room_code = response_data["room_code"]
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    mock_redis.exists.assert_awaited_once_with(meta_key)
    mock_redis.set_json.assert_awaited_once()
    mock_redis.hset_model.assert_awaited_once()
    # Ensure expire was called for the players hash key only
    # set_json handles expiry for the meta key internally
    # mock_redis.expire.assert_any_await(meta_key, 3600) # No longer needed
    mock_redis.expire.assert_awaited_once_with(players_key, 3600)
    # assert mock_redis.expire.await_count == 2 # Should only be 1 explicit call

    # Check the data passed to Redis (optional detailed check)
    # meta_call_args = mock_redis.set_json.await_args[0]
    # player_call_args = mock_redis.hset_model.await_args[0]
    # assert isinstance(meta_call_args[1], RoomMeta)
    # assert meta_call_args[1].host_nickname == "TestHost"
    # assert isinstance(player_call_args[2], Player)
    # assert player_call_args[2].nickname == "TestHost"


def test_create_room_code_collision(mock_redis: AsyncMock) -> None:
    """Test handling of room code generation collision (highly unlikely)."""
    # Make exists return True repeatedly to simulate collision
    mock_redis.exists = AsyncMock(return_value=True)

    request_data = RoomCreateRequest(host_nickname="TestHost")
    response = client.post("/api/v0/rooms", json=request_data.model_dump())

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Could not generate a unique room code" in response.json()["detail"]
    assert mock_redis.exists.await_count == 5  # Max retries


# Test POST /api/v0/rooms/{code}/join
def test_join_room_success(mock_redis: AsyncMock) -> None:
    """Test successfully joining an existing room."""
    room_code = "ABCD"
    nickname = "TestJoiner"
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    # Setup mock: Room exists, nickname doesn't
    mock_redis.exists = AsyncMock(return_value=True)  # Room meta key exists
    mock_redis.hget_model = AsyncMock(return_value=None)  # Nickname doesn't exist in hash

    request_data = RoomJoinRequest(nickname=nickname)
    response = client.post(f"/api/v0/rooms/{room_code}/join", json=request_data.model_dump())

    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "ws_url" in response_data
    assert response_data["ws_url"].endswith(f"/ws/{room_code}/{nickname}")

    # Verify Redis calls
    mock_redis.exists.assert_awaited_once_with(meta_key)
    mock_redis.hget_model.assert_awaited_once_with(players_key, nickname, Player)
    mock_redis.hset_model.assert_awaited_once()  # New player added
    # Check player data added
    # added_player_args = mock_redis.hset_model.await_args[0]
    # assert isinstance(added_player_args[2], Player)
    # assert added_player_args[2].nickname == nickname
    mock_redis.expire.assert_any_await(meta_key, 3600)
    mock_redis.expire.assert_any_await(players_key, 3600)
    assert mock_redis.expire.await_count == 2


def test_join_room_not_found(mock_redis: AsyncMock) -> None:
    """Test joining a room that doesn't exist."""
    room_code = "WXYZ"
    meta_key = f"room:{room_code}:meta"

    # Setup mock: Room meta key doesn't exist
    mock_redis.exists = AsyncMock(return_value=False)

    request_data = RoomJoinRequest(nickname="TestJoiner")
    response = client.post(f"/api/v0/rooms/{room_code}/join", json=request_data.model_dump())

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert f"Room '{room_code}' not found" in response.json()["detail"]
    mock_redis.exists.assert_awaited_once_with(meta_key)
    mock_redis.hget_model.assert_not_awaited()
    mock_redis.hset_model.assert_not_awaited()


def test_join_room_nickname_conflict(mock_redis: AsyncMock) -> None:
    """Test joining a room with a nickname that's already taken."""
    room_code = "QWER"
    nickname = "ExistingPlayer"
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    # Setup mock: Room exists, nickname already present in players hash
    mock_redis.exists = AsyncMock(return_value=True)  # Room exists
    existing_player_data = Player(nickname=nickname, score=50, connected=True)
    mock_redis.hget_model = AsyncMock(return_value=existing_player_data)  # Nickname exists

    request_data = RoomJoinRequest(nickname=nickname)
    response = client.post(f"/api/v0/rooms/{room_code}/join", json=request_data.model_dump())

    assert response.status_code == status.HTTP_409_CONFLICT
    assert f"Nickname '{nickname}' is already taken" in response.json()["detail"]
    mock_redis.exists.assert_awaited_once_with(meta_key)
    mock_redis.hget_model.assert_awaited_once_with(players_key, nickname, Player)
    mock_redis.hset_model.assert_not_awaited()


# TODO: Add basic WebSocket connection test later if desired

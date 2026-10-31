import logging

import pytest
from fastapi import status

# Import AsyncClient for type hint
from httpx import AsyncClient
from pytest import MonkeyPatch

# Import your FastAPI app and schemas/models
# No need to import app here if test_client fixture handles it
from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import RoundData, RoundStateEnum

# Import WebSocket schemas
from backend.schemas.ws import WSMessage

# Import room_service for test setup
from backend.services import room_service
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)
# Assume test_client and redis_client fixtures are available from conftest.py

pytestmark = pytest.mark.asyncio

# --- WebSocket Test Helper --- #


async def ws_send_receive(
    ws_session: AsyncClient, send_type: str, send_payload: dict | None = None
) -> dict:
    """Helper to send a WSMessage and receive the next one."""
    msg_to_send = WSMessage(type=send_type, payload=send_payload or {}).model_dump()
    await ws_session.send_json(msg_to_send)
    response_data = await ws_session.receive_json()
    return response_data


# --- Test Cases for POST /api/v0/rooms --- #


async def test_create_room_success(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test successful creation of a new game room."""
    # Mock generate_room_code to return a predictable code
    monkeypatch.setattr("backend.routes.rooms.generate_room_code", lambda: "ABCD")
    # Mock RedisClient dependency injection
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    # Patch where room_service uses RedisClient directly (if applicable, good practice)
    # If room_service took redis as an arg, this might not be needed, but safe to include
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    # Prepare request data - Use Enum.value for JSON serialization
    request_data = {
        "host_nickname": "HostUser",
        "mode": ScoringMode.DISTANCE.value,  # Send the string value
        "round_timeout_seconds": 45,
    }

    # Make the request
    response = await test_client.post("/api/v0/rooms", json=request_data)

    # Assertions for the response
    assert response.status_code == status.HTTP_201_CREATED
    response_data = response.json()
    assert response_data["room_code"] == "ABCD"
    assert "ws_url" in response_data
    assert "ws://testserver/api/v0/rooms/ws/ABCD/HostUser" in response_data["ws_url"]
    assert response.headers["location"] == response_data["ws_url"]

    # Assertions for Redis interactions
    meta_key = "room:ABCD:meta"
    players_key = "room:ABCD:players"

    # Check RoomMeta was set correctly - use get_model
    room_meta = await redis_client.get_model(meta_key, RoomMeta)
    assert room_meta is not None
    assert room_meta.host_nickname == "HostUser"
    assert room_meta.mode == ScoringMode.DISTANCE  # Pydantic should load it back as Enum
    assert room_meta.round_timeout_seconds == 45

    # Check Host Player was added correctly via room_service.add_player
    # Use hget_model
    host_player = await redis_client.hget_model(players_key, "HostUser", Player)
    assert host_player is not None
    assert host_player.nickname == "HostUser"
    assert host_player.score == 0
    assert not host_player.connected


async def test_create_room_collision_retry(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test that room creation retries if the first generated code exists."""
    # Mock generate_room_code to return colliding then unique codes
    codes_to_return = ["COLL", "ABCD"]
    monkeypatch.setattr("backend.routes.rooms.generate_room_code", lambda: codes_to_return.pop(0))

    # Mock RedisClient dependency injection
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    # Pre-populate Redis to simulate collision using a simple string value with set_raw
    # Or adjust set_json; for now, let's assume set_raw exists or use a simple Pydantic
    # model if needed.
    # Let's use set_json with a simple dummy model for now if set_raw isn't available.
    # NOTE: This assumes RedisClient has a set_raw or similar, or we adjust set_json.
    # Using set_json with a dict won't work directly. We'll store a simple string via the
    # underlying connection for the test.
    async with await redis_client.get_connection() as conn:
        await conn.set(
            "room:COLL:meta", '{"some": "data"}'
        )  # Use underlying connection for raw set

    request_data = {
        "host_nickname": "RetryHost",
        "mode": ScoringMode.EXACT.value,
        "round_timeout_seconds": 60,
    }

    response = await test_client.post("/api/v0/rooms", json=request_data)

    assert response.status_code == status.HTTP_201_CREATED
    assert not codes_to_return  # Check both codes were popped
    response_data = response.json()
    assert response_data["room_code"] == "ABCD"

    # Check Redis has the new room data under the second code
    assert await redis_client.exists("room:ABCD:meta")
    assert await redis_client.exists("room:ABCD:players")
    # Check the raw value we set earlier
    async with await redis_client.get_connection() as conn:
        coll_value = await conn.get("room:COLL:meta")
        assert coll_value == b'{"some": "data"}'


async def test_create_room_max_retries_exceeded(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test that room creation fails if max retries for unique code are exceeded."""
    # Mock generate_room_code to always return colliding codes
    monkeypatch.setattr("backend.routes.rooms.generate_room_code", lambda: "FAIL")

    # Mock RedisClient dependency injection
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    # Pre-populate Redis to ensure collision using the underlying connection
    async with await redis_client.get_connection() as conn:
        await conn.set("room:FAIL:meta", '{"data": "exists"}')

    request_data = {
        "host_nickname": "FailHost",
        "mode": ScoringMode.EXACT.value,
        "round_timeout_seconds": 30,
    }

    response = await test_client.post("/api/v0/rooms", json=request_data)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert "Could not generate a unique room code" in response.text


# --- Helper for join tests --- #


async def setup_existing_room(
    redis_instance: RedisClient, room_code: str = "JOIN", host_nick: str = "Host"
) -> tuple[str, str]:
    """Helper to set up an existing room in Redis for join tests."""
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"
    room_ttl = 3600

    # Use Enum member when creating the model instance directly
    room_meta = RoomMeta(
        host_nickname=host_nick, mode=ScoringMode.DISTANCE, round_timeout_seconds=30
    )
    host_player = Player(nickname=host_nick, connected=True)

    await redis_instance.set_json(meta_key, room_meta, expire_seconds=room_ttl)
    await redis_instance.hset_model(players_key, host_nick, host_player)
    await redis_instance.expire(players_key, room_ttl)
    return room_code, host_nick


# --- Tests for POST /api/v0/rooms/{code}/join --- #


async def test_join_room_success(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test successfully joining an existing room."""
    # Mock Redis dependency
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    # Setup existing room using helper
    room_code, host_nick = await setup_existing_room(redis_client, room_code="COOL")

    request_data = {"nickname": "NewPlayer"}

    # Make the request
    response = await test_client.post(f"/api/v0/rooms/{room_code}/join", json=request_data)

    # Assertions for response
    assert response.status_code == status.HTTP_200_OK
    response_data = response.json()
    assert "ws_url" in response_data
    assert f"ws://testserver/api/v0/rooms/ws/{room_code}/NewPlayer" in response_data["ws_url"]

    # Assertions for Redis state
    players_key = f"room:{room_code}:players"
    # Use hget_model to check player data
    new_player = await redis_client.hget_model(players_key, "NewPlayer", Player)
    assert new_player is not None
    assert new_player.nickname == "NewPlayer"
    assert not new_player.connected
    # Check count using hgetall_models
    all_players = await redis_client.hgetall_models(players_key, Player)
    assert len(all_players) == 2  # Host + NewPlayer


async def test_join_room_not_found(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test attempting to join a room that does not exist."""
    # Mock Redis dependency
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    room_code = "FAKE"
    # Ensure room doesn't exist (redis_client fixture ensures fresh state)
    assert not await redis_client.exists(f"room:{room_code}:meta")

    request_data = {"nickname": "WannabePlayer"}

    response = await test_client.post(f"/api/v0/rooms/{room_code}/join", json=request_data)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert f"Room '{room_code}' not found" in response.text


async def test_join_room_nickname_taken(
    test_client: AsyncClient, monkeypatch: MonkeyPatch, redis_client: RedisClient
) -> None:
    """Test attempting to join a room with a nickname that is already taken."""
    # Mock Redis dependency
    monkeypatch.setattr("backend.routes.rooms.get_redis", lambda: redis_client)
    monkeypatch.setattr(
        "backend.services.room_service.RedisClient", lambda: redis_client, raising=False
    )

    # Setup existing room
    room_code, host_nick = await setup_existing_room(redis_client, room_code="BUSY")

    # Attempt to join with the host's nickname
    request_data = {"nickname": host_nick}

    response = await test_client.post(f"/api/v0/rooms/{room_code}/join", json=request_data)

    assert response.status_code == status.HTTP_409_CONFLICT
    assert f"Nickname '{host_nick}' is already taken" in response.text
    players_key = f"room:{room_code}:players"
    # Check count using hgetall_models
    all_players = await redis_client.hgetall_models(players_key, Player)
    assert len(all_players) == 1  # Ensure only host exists


# --- Room state is not exposed over REST --- #


async def setup_room_with_active_round(redis_instance: RedisClient, room_code: str) -> None:
    """Helper to set up a room whose current round holds a secret answer (KJFK)."""
    await setup_existing_room(redis_instance, room_code=room_code)
    await room_service.set_round_data(
        redis_instance,
        room_code,
        RoundData(
            state=RoundStateEnum.ACCEPTING_GUESSES,
            selected_plane_hex="abc123",
            correct_airport_code="KJFK",
            guess_direction="destination",
        ),
    )


async def test_room_state_is_not_readable_over_rest(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """GET on a live room code matches no endpoint, so the round answer stays private."""
    await setup_room_with_active_round(redis_client, room_code="SECR")

    response = await test_client.get("/api/v0/rooms/SECR")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "KJFK" not in response.text


async def test_room_cannot_be_deleted_over_rest(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """DELETE on a live room code matches no endpoint and leaves the room intact."""
    await setup_room_with_active_round(redis_client, room_code="KEEP")

    response = await test_client.delete("/api/v0/rooms/KEEP")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await room_service.get_room_meta(redis_client, "KEEP") is not None


# --- Host Validation Tests --- #


async def test_host_validation_after_transfer(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test that host validation correctly checks Redis after host transfer."""
    # Create a room
    create_resp = await test_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": "OriginalHost",
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 30,
        },
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    room_code = create_resp.json()["room_code"]

    # Join as another player
    join_resp = await test_client.post(
        f"/api/v0/rooms/{room_code}/join", json={"nickname": "NewHost"}
    )
    assert join_resp.status_code == status.HTTP_200_OK

    # Simulate host transfer by updating room meta
    room_meta = await redis_client.get_model(f"room:{room_code}:meta", RoomMeta)
    assert room_meta is not None
    room_meta.host_nickname = "NewHost"
    await redis_client.set_json(f"room:{room_code}:meta", room_meta)

    # Verify the host has been updated
    updated_meta = await redis_client.get_model(f"room:{room_code}:meta", RoomMeta)
    assert updated_meta is not None
    assert updated_meta.host_nickname == "NewHost"


async def test_host_validation_with_missing_room(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test host validation when room metadata is missing."""
    # Create a room initially
    create_resp = await test_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": "TestHost",
            "mode": ScoringMode.EXACT.value,
            "round_timeout_seconds": 30,
        },
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    room_code = create_resp.json()["room_code"]

    # Delete the room metadata to simulate missing room
    await redis_client.delete(f"room:{room_code}:meta")

    # Verify room meta is gone
    room_meta = await redis_client.get_model(f"room:{room_code}:meta", RoomMeta)
    assert room_meta is None


async def test_host_validation_with_multiple_transfers(
    test_client: AsyncClient, redis_client: RedisClient
) -> None:
    """Test host validation through multiple host transfers."""
    # Create a room
    create_resp = await test_client.post(
        "/api/v0/rooms",
        json={
            "host_nickname": "Host1",
            "mode": ScoringMode.DISTANCE.value,
            "round_timeout_seconds": 30,
        },
    )
    assert create_resp.status_code == status.HTTP_201_CREATED
    room_code = create_resp.json()["room_code"]

    # Join multiple players
    for i in range(2, 5):
        join_resp = await test_client.post(
            f"/api/v0/rooms/{room_code}/join", json={"nickname": f"Host{i}"}
        )
        assert join_resp.status_code == status.HTTP_200_OK

    # Simulate multiple host transfers
    for i in range(2, 5):
        room_meta = await redis_client.get_model(f"room:{room_code}:meta", RoomMeta)
        assert room_meta is not None
        room_meta.host_nickname = f"Host{i}"
        await redis_client.set_json(f"room:{room_code}:meta", room_meta)

        # Verify the host has been updated
        updated_meta = await redis_client.get_model(f"room:{room_code}:meta", RoomMeta)
        assert updated_meta is not None
        assert updated_meta.host_nickname == f"Host{i}"

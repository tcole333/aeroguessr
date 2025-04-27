"""Integration tests for the room_service using a real Redis instance."""

import time

import pytest

from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import PlayerGuess, RoundData, RoundStateEnum
from backend.services import room_service
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async and needing the redis_client fixture
# Also mark them as integration tests
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.usefixtures("redis_client"),
    pytest.mark.integration,  # Add integration marker
]


# --- Test Cases --- #


async def test_add_get_player(redis_client: RedisClient) -> None:  # Fixture is injected
    room_code = "AGP1"
    nickname = "Tester1"
    player = Player(nickname=nickname, score=10, connected=False)

    # Add player
    await room_service.add_player(redis_client, room_code, player)

    # Get player
    retrieved_player = await room_service.get_player(redis_client, room_code, nickname)

    assert retrieved_player is not None
    assert retrieved_player.nickname == nickname
    assert retrieved_player.score == 10
    assert retrieved_player.connected is False
    assert retrieved_player.last_seen_ts is None

    # Get non-existent player
    non_existent = await room_service.get_player(redis_client, room_code, "Nobody")
    assert non_existent is None


async def test_update_player_status(redis_client: RedisClient) -> None:
    """Test updating player status."""
    room_code = "UPS1"
    nickname = "TesterStatus"
    player = Player(nickname=nickname, score=0, connected=False)
    await room_service.add_player(redis_client, room_code, player)

    # Update status to connected
    before_update_ts = time.time()
    updated_player = await room_service.update_player_status(
        redis_client, room_code, nickname, connected=True
    )
    after_update_ts = time.time()

    assert updated_player is not None
    assert updated_player.connected is True
    assert updated_player.last_seen_ts is not None
    assert before_update_ts <= updated_player.last_seen_ts <= after_update_ts

    # Verify in Redis
    retrieved_player = await room_service.get_player(redis_client, room_code, nickname)
    assert retrieved_player is not None
    assert retrieved_player.connected is True
    assert retrieved_player.last_seen_ts == updated_player.last_seen_ts

    # Update status for non-existent player
    result = await room_service.update_player_status(
        redis_client, room_code, "Nobody", connected=True
    )
    assert result is None


async def test_update_player_score(redis_client: RedisClient) -> None:
    """Test updating player score."""
    room_code = "USC1"
    nickname = "TesterScore"
    player = Player(nickname=nickname, score=50, connected=True, last_seen_ts=time.time() - 10)
    await room_service.add_player(redis_client, room_code, player)

    # Add score
    before_update_ts = time.time()
    updated_player = await room_service.update_player_score(
        redis_client, room_code, nickname, score_change=25
    )
    after_update_ts = time.time()

    assert updated_player is not None
    assert updated_player.score == 75
    # Check last_seen_ts was also updated
    assert updated_player.last_seen_ts is not None
    assert before_update_ts <= updated_player.last_seen_ts <= after_update_ts

    # Verify in Redis
    retrieved_player = await room_service.get_player(redis_client, room_code, nickname)
    assert retrieved_player is not None
    assert retrieved_player.score == 75
    assert retrieved_player.last_seen_ts == updated_player.last_seen_ts

    # Update score for non-existent player
    result = await room_service.update_player_score(
        redis_client, room_code, "Nobody", score_change=100
    )
    assert result is None


async def test_get_all_players(redis_client: RedisClient) -> None:
    """Test getting all players."""
    room_code = "GAP1"
    player1 = Player(nickname="P1", score=10)
    player2 = Player(nickname="P2", score=20, connected=True)

    await room_service.add_player(redis_client, room_code, player1)
    await room_service.add_player(redis_client, room_code, player2)

    all_players = await room_service.get_all_players(redis_client, room_code)

    assert len(all_players) == 2
    assert "P1" in all_players
    assert "P2" in all_players
    assert all_players["P1"].score == 10
    assert all_players["P2"].score == 20
    assert all_players["P1"].connected is False
    assert all_players["P2"].connected is True

    # Test empty room
    empty_room_players = await room_service.get_all_players(redis_client, "EMPTY")
    assert len(empty_room_players) == 0


async def test_remove_player(redis_client: RedisClient) -> None:
    """Test removing a player."""
    room_code = "RMP1"
    nickname = "TesterRemove"
    player = Player(nickname=nickname)
    await room_service.add_player(redis_client, room_code, player)

    # Ensure player exists
    assert await room_service.get_player(redis_client, room_code, nickname) is not None

    # Remove player
    deleted = await room_service.remove_player(redis_client, room_code, nickname)
    assert deleted is True

    # Ensure player is gone
    assert await room_service.get_player(redis_client, room_code, nickname) is None

    # Remove non-existent player
    deleted_again = await room_service.remove_player(redis_client, room_code, nickname)
    assert deleted_again is False
    deleted_nobody = await room_service.remove_player(redis_client, room_code, "Nobody")
    assert deleted_nobody is False


async def test_set_get_room_meta(redis_client: RedisClient) -> None:
    """Test setting and getting room metadata."""
    room_code = "SGM1"
    meta = RoomMeta(mode=ScoringMode.DISTANCE, round_timeout_seconds=45, host_nickname="MetaHost")

    # Set meta
    await room_service.set_room_meta(redis_client, room_code, meta)

    # Get meta
    retrieved_meta = await room_service.get_room_meta(redis_client, room_code)

    assert retrieved_meta is not None
    assert retrieved_meta.mode == ScoringMode.DISTANCE
    assert retrieved_meta.round_timeout_seconds == 45
    assert retrieved_meta.host_nickname == "MetaHost"
    assert retrieved_meta.created_ts is not None  # Check default factory worked

    # Get non-existent meta
    non_existent = await room_service.get_room_meta(redis_client, "NONEXIST")
    assert non_existent is None


async def test_set_get_round_data(redis_client: RedisClient) -> None:
    """Test setting and getting round data."""
    room_code = "SGRD1"
    guess = PlayerGuess(nickname="Guesser", guess="JFK")
    round_data = RoundData(
        state=RoundStateEnum.ACCEPTING_GUESSES,
        selected_plane_hex="abcdef",
        correct_airport_code="BOS",
        guess_direction="origin",
        round_start_time=time.time(),
        guesses={"Guesser": guess},
        round_number=5,
    )

    # Set round data
    await room_service.set_round_data(redis_client, room_code, round_data)

    # Get round data
    retrieved_data = await room_service.get_round_data(redis_client, room_code)

    assert retrieved_data is not None
    assert retrieved_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert retrieved_data.selected_plane_hex == "abcdef"
    assert retrieved_data.correct_airport_code == "BOS"
    assert retrieved_data.guess_direction == "origin"
    assert retrieved_data.round_start_time == round_data.round_start_time
    assert len(retrieved_data.guesses) == 1
    assert "Guesser" in retrieved_data.guesses
    assert retrieved_data.guesses["Guesser"].guess == "JFK"
    assert retrieved_data.results is None
    assert retrieved_data.round_number == 5

    # Get non-existent round data
    non_existent = await room_service.get_round_data(redis_client, "NOROUND")
    assert non_existent is None


async def test_initialize_round_data(redis_client: RedisClient) -> None:
    """Test initializing round data."""
    room_code = "IRD1"

    # Initialize first time
    initialized_data = await room_service.initialize_round_data(redis_client, room_code)
    assert initialized_data is not None
    assert initialized_data.state == RoundStateEnum.WAITING_FOR_SELECTION
    assert initialized_data.round_number == 0
    assert initialized_data.selected_plane_hex is None
    assert len(initialized_data.guesses) == 0

    # Verify it was stored
    stored_data = await room_service.get_round_data(redis_client, room_code)
    assert stored_data == initialized_data

    # Modify stored data
    stored_data.round_number = 1
    stored_data.state = RoundStateEnum.ACCEPTING_GUESSES
    await room_service.set_round_data(redis_client, room_code, stored_data)

    # Call initialize again - should return existing modified data
    reinitialized_data = await room_service.initialize_round_data(redis_client, room_code)
    assert reinitialized_data is not None
    assert reinitialized_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert reinitialized_data.round_number == 1

    reinitialized_data = await room_service.initialize_round_data(redis_client, room_code)
    assert reinitialized_data is not None
    assert reinitialized_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert reinitialized_data.round_number == 1


# </rewritten_file>

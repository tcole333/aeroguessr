"""Integration tests for room_service against a real Redis (TEST_REDIS_URL, see tests/README.md).

They run in the integration suite because fakeredis does not show how a real server and the
production decode_responses client behave.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable

import pytest
import pytest_asyncio
import redis.asyncio as redis
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.typing import EncodableT

from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import PlayerGuess, RoundData, RoundStateEnum
from backend.services import room_service
from backend.utils.redis_async import RedisClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# --- Test Cases --- #


async def test_add_get_player(real_redis_client: RedisClient) -> None:
    room_code = "AGP1"
    nickname = "Tester1"
    player = Player(nickname=nickname, score=10, connected=False)

    # Add player
    await room_service.add_player(real_redis_client, room_code, player)

    # Get player
    retrieved_player = await room_service.get_player(real_redis_client, room_code, nickname)

    assert retrieved_player is not None
    assert retrieved_player.nickname == nickname
    assert retrieved_player.score == 10
    assert retrieved_player.connected is False
    assert retrieved_player.last_seen_ts is None

    # Get non-existent player
    non_existent = await room_service.get_player(real_redis_client, room_code, "Nobody")
    assert non_existent is None


async def test_update_player_status(real_redis_client: RedisClient) -> None:
    """Test updating player status."""
    room_code = "UPS1"
    nickname = "TesterStatus"
    player = Player(nickname=nickname, score=0, connected=False)
    await room_service.add_player(real_redis_client, room_code, player)

    # Update status to connected
    before_update_ts = time.time()
    updated_player = await room_service.update_player_status(
        real_redis_client, room_code, nickname, connected=True
    )
    after_update_ts = time.time()

    assert updated_player is not None
    assert updated_player.connected is True
    assert updated_player.last_seen_ts is not None
    assert before_update_ts <= updated_player.last_seen_ts <= after_update_ts

    # Verify in Redis
    retrieved_player = await room_service.get_player(real_redis_client, room_code, nickname)
    assert retrieved_player is not None
    assert retrieved_player.connected is True
    assert retrieved_player.last_seen_ts == updated_player.last_seen_ts

    # Update status for non-existent player
    result = await room_service.update_player_status(
        real_redis_client, room_code, "Nobody", connected=True
    )
    assert result is None


async def test_update_player_score(real_redis_client: RedisClient) -> None:
    """Test updating player score."""
    room_code = "USC1"
    nickname = "TesterScore"
    player = Player(nickname=nickname, score=50, connected=True, last_seen_ts=time.time() - 10)
    await room_service.add_player(real_redis_client, room_code, player)

    # Add score
    before_update_ts = time.time()
    updated_player = await room_service.update_player_score(
        real_redis_client, room_code, nickname, score_change=25
    )
    after_update_ts = time.time()

    assert updated_player is not None
    assert updated_player.score == 75
    # Check last_seen_ts was also updated
    assert updated_player.last_seen_ts is not None
    assert before_update_ts <= updated_player.last_seen_ts <= after_update_ts

    # Verify in Redis
    retrieved_player = await room_service.get_player(real_redis_client, room_code, nickname)
    assert retrieved_player is not None
    assert retrieved_player.score == 75
    assert retrieved_player.last_seen_ts == updated_player.last_seen_ts

    # Update score for non-existent player
    result = await room_service.update_player_score(
        real_redis_client, room_code, "Nobody", score_change=100
    )
    assert result is None


async def test_get_all_players(real_redis_client: RedisClient) -> None:
    """Test getting all players."""
    room_code = "GAP1"
    player1 = Player(nickname="P1", score=10)
    player2 = Player(nickname="P2", score=20, connected=True)

    await room_service.add_player(real_redis_client, room_code, player1)
    await room_service.add_player(real_redis_client, room_code, player2)

    all_players = await room_service.get_all_players(real_redis_client, room_code)

    assert len(all_players) == 2
    assert "P1" in all_players
    assert "P2" in all_players
    assert all_players["P1"].score == 10
    assert all_players["P2"].score == 20
    assert all_players["P1"].connected is False
    assert all_players["P2"].connected is True

    # Test empty room
    empty_room_players = await room_service.get_all_players(real_redis_client, "EMPTY")
    assert len(empty_room_players) == 0


async def test_set_get_room_meta(real_redis_client: RedisClient) -> None:
    """Test setting and getting room metadata."""
    room_code = "SGM1"
    meta = RoomMeta(mode=ScoringMode.DISTANCE, round_timeout_seconds=45, host_nickname="MetaHost")

    # Set meta
    await room_service.set_room_meta(real_redis_client, room_code, meta)

    # Get meta
    retrieved_meta = await room_service.get_room_meta(real_redis_client, room_code)

    assert retrieved_meta is not None
    assert retrieved_meta.mode == ScoringMode.DISTANCE
    assert retrieved_meta.round_timeout_seconds == 45
    assert retrieved_meta.host_nickname == "MetaHost"
    assert retrieved_meta.created_ts is not None  # Check default factory worked

    # Get non-existent meta
    non_existent = await room_service.get_room_meta(real_redis_client, "NONEXIST")
    assert non_existent is None


async def test_set_get_round_data(real_redis_client: RedisClient) -> None:
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
    await room_service.set_round_data(real_redis_client, room_code, round_data)

    # Get round data
    retrieved_data = await room_service.get_round_data(real_redis_client, room_code)

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
    non_existent = await room_service.get_round_data(real_redis_client, "NOROUND")
    assert non_existent is None


async def test_initialize_round_data(real_redis_client: RedisClient) -> None:
    """Test initializing round data."""
    room_code = "IRD1"

    # Initialize first time
    initialized_data = await room_service.initialize_round_data(real_redis_client, room_code)
    assert initialized_data is not None
    assert initialized_data.state == RoundStateEnum.WAITING_FOR_SELECTION
    assert initialized_data.round_number == 0
    assert initialized_data.selected_plane_hex is None
    assert len(initialized_data.guesses) == 0

    # Verify it was stored
    stored_data = await room_service.get_round_data(real_redis_client, room_code)
    assert stored_data == initialized_data

    # Modify stored data
    stored_data.round_number = 1
    stored_data.state = RoundStateEnum.ACCEPTING_GUESSES
    await room_service.set_round_data(real_redis_client, room_code, stored_data)

    # Call initialize again - should return existing modified data
    reinitialized_data = await room_service.initialize_round_data(real_redis_client, room_code)
    assert reinitialized_data is not None
    assert reinitialized_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert reinitialized_data.round_number == 1

    reinitialized_data = await room_service.initialize_round_data(real_redis_client, room_code)
    assert reinitialized_data is not None
    assert reinitialized_data.state == RoundStateEnum.ACCEPTING_GUESSES
    assert reinitialized_data.round_number == 1


async def _start_accepting_round(redis_client: RedisClient, room_code: str) -> None:
    await room_service.set_round_data(
        redis_client,
        room_code,
        RoundData(state=RoundStateEnum.ACCEPTING_GUESSES, correct_airport_code="KJFK"),
    )


async def test_record_guess_keeps_every_concurrent_guess(real_redis_client: RedisClient) -> None:
    """Simultaneous guesses from different players are all stored."""
    room_code = "RGC1"
    await _start_accepting_round(real_redis_client, room_code)
    nicknames = [f"Player{i}" for i in range(20)]

    outcomes = await asyncio.gather(
        *(
            room_service.record_guess(
                real_redis_client, room_code, PlayerGuess(nickname=nick, guess="KJFK")
            )
            for nick in nicknames
        )
    )

    assert [outcome for outcome, _ in outcomes] == [room_service.GuessOutcome.RECORDED] * 20
    stored = await room_service.get_round_data(real_redis_client, room_code)
    assert stored is not None
    assert set(stored.guesses) == set(nicknames)


async def test_record_guess_rejects_second_guess(real_redis_client: RedisClient) -> None:
    room_code = "RGS1"
    await _start_accepting_round(real_redis_client, room_code)
    await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Repeat", guess="KJFK")
    )

    outcome, _ = await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Repeat", guess="KLAX")
    )

    assert outcome == room_service.GuessOutcome.ALREADY_GUESSED
    stored = await room_service.get_round_data(real_redis_client, room_code)
    assert stored is not None
    assert stored.guesses["Repeat"].guess == "KJFK"


async def test_record_guess_rejects_guess_outside_round(real_redis_client: RedisClient) -> None:
    room_code = "RGO1"
    await room_service.initialize_round_data(real_redis_client, room_code)

    outcome, _ = await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Early", guess="KJFK")
    )

    assert outcome == room_service.GuessOutcome.NOT_ACCEPTING
    stored = await room_service.get_round_data(real_redis_client, room_code)
    assert stored is not None
    assert stored.guesses == {}


async def test_record_guess_without_round(real_redis_client: RedisClient) -> None:
    outcome, round_data = await room_service.record_guess(
        real_redis_client, "NORD", PlayerGuess(nickname="Lost", guess="KJFK")
    )

    assert (outcome, round_data) == (room_service.GuessOutcome.NO_ROUND, None)


async def test_record_guess_rejects_unknown_airport(real_redis_client: RedisClient) -> None:
    room_code = "RGU1"
    await _start_accepting_round(real_redis_client, room_code)

    outcome, _ = await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Typo", guess="ZZZ")
    )

    assert outcome == room_service.GuessOutcome.UNKNOWN_AIRPORT
    stored = await room_service.get_round_data(real_redis_client, room_code)
    assert stored is not None
    assert stored.guesses == {}


async def test_record_guess_reports_duplicate_before_unknown_airport(
    real_redis_client: RedisClient,
) -> None:
    room_code = "RGU2"
    await _start_accepting_round(real_redis_client, room_code)
    await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Repeat", guess="KJFK")
    )

    outcome, _ = await room_service.record_guess(
        real_redis_client, room_code, PlayerGuess(nickname="Repeat", guess="ZZZ")
    )

    assert outcome == room_service.GuessOutcome.ALREADY_GUESSED


# --- Player writes racing other clients (#219) --- #

Command = tuple[object, ...] | None
AfterReply = Callable[[Command], Awaitable[None]]


@pytest_asyncio.fixture
async def client_with_reply_hook(
    real_redis: redis.Redis,
) -> AsyncIterator[Callable[[AfterReply], RedisClient]]:
    """Build a RedisClient whose connections await ``after_reply(command)`` after every reply.

    Each reply is a point where another client can change the data, or where a cancelled
    caller would stop. A test can act at exactly that point instead of racing timers.
    ``command`` is the command just answered, or None inside a pipelined transaction.
    """
    pools: list[redis.ConnectionPool] = []

    def build(after_reply: AfterReply) -> RedisClient:
        class ReplyHookConnection(redis.Connection):
            last_command: Command = None

            async def send_packed_command(
                self, command: bytes | str | Iterable[bytes], check_health: bool = True
            ) -> None:
                self.last_command = None
                await super().send_packed_command(command, check_health)

            async def send_command(self, *args: EncodableT, **kwargs: bool) -> None:
                await super().send_command(*args, **kwargs)
                self.last_command = args

            async def read_response(self, *args: object, **kwargs: object) -> object:
                response = await super().read_response(*args, **kwargs)
                await after_reply(self.last_command)
                return response

        pool = redis.ConnectionPool(
            connection_class=ReplyHookConnection, **real_redis.connection_pool.connection_kwargs
        )
        pools.append(pool)
        return RedisClient(redis.Redis(connection_pool=pool))

    yield build
    for pool in pools:
        await pool.disconnect()


class OnceAfterPlayerRead:
    """Runs ``action`` once, right after the first HGET on ``players_key`` is answered."""

    def __init__(self, players_key: str, action: Callable[[], Awaitable[object]]) -> None:
        self.players_key = players_key
        self.action = action
        self.fired = False

    async def __call__(self, command: Command) -> None:
        if self.fired or command is None or command[:2] != ("HGET", self.players_key):
            return
        self.fired = True
        await self.action()


class LoseExecReply:
    """Raises a reply timeout once, right after a WATCHed write's EXEC is answered.

    EXEC has run on the server, but the caller never sees its result, as when the reply is
    late or the event loop stalls past the socket timeout. A transaction's replies all come
    with ``command`` None: MULTI, the one queued write, then EXEC.
    """

    def __init__(self) -> None:
        self.transaction_replies = 0
        self.fired = False

    async def __call__(self, command: Command) -> None:
        if self.fired or command is not None:
            return
        self.transaction_replies += 1
        if self.transaction_replies == 3:
            self.fired = True
            raise RedisTimeoutError("Timeout reading from socket")


PlayerUpdate = Callable[[RedisClient, str, str], Awaitable[Player | None]]


async def _set_disconnected(client: RedisClient, room_code: str, nickname: str) -> Player | None:
    return await room_service.update_player_status(client, room_code, nickname, connected=False)


async def _award_points(client: RedisClient, room_code: str, nickname: str) -> Player | None:
    return await room_service.update_player_score(client, room_code, nickname, score_change=10)


PLAYER_UPDATES = pytest.mark.parametrize(
    "update", [_set_disconnected, _award_points], ids=["status", "score"]
)


@PLAYER_UPDATES
async def test_update_racing_room_deletion_does_not_recreate_players(
    update: PlayerUpdate,
    real_redis: redis.Redis,
    real_redis_client: RedisClient,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    """A room deleted after the player is read stays deleted, instead of coming back with no TTL."""
    room_code = "RDEL"
    players_key = f"room:{room_code}:players"
    await room_service.add_player(real_redis_client, room_code, Player(nickname="Leaver"))
    delete_room = OnceAfterPlayerRead(
        players_key, lambda: room_service.delete_room(real_redis_client, room_code)
    )

    result = await update(client_with_reply_hook(delete_room), room_code, "Leaver")

    assert delete_room.fired
    assert await real_redis.exists(players_key) == 0
    assert result is None


@PLAYER_UPDATES
async def test_update_racing_player_removal_does_not_bring_them_back(
    update: PlayerUpdate,
    real_redis: redis.Redis,
    real_redis_client: RedisClient,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    """A player gone from a hash that still exists is not written back by the update.

    Nothing in the app removes a single player, so another client deletes the field directly.
    """
    room_code = "RREM"
    players_key = f"room:{room_code}:players"
    for nickname in ("Stayer", "Leaver"):
        await room_service.add_player(real_redis_client, room_code, Player(nickname=nickname))
    remove_leaver = OnceAfterPlayerRead(players_key, lambda: real_redis.hdel(players_key, "Leaver"))

    result = await update(client_with_reply_hook(remove_leaver), room_code, "Leaver")

    assert remove_leaver.fired
    assert await real_redis.hkeys(players_key) == ["Stayer"]
    assert result is None


async def test_status_update_keeps_points_awarded_meanwhile(
    real_redis_client: RedisClient,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    room_code = "RSCO"
    players_key = f"room:{room_code}:players"
    await room_service.add_player(real_redis_client, room_code, Player(nickname="Racer"))
    award_points = OnceAfterPlayerRead(
        players_key,
        lambda: room_service.update_player_score(real_redis_client, room_code, "Racer", 40),
    )

    updated = await room_service.update_player_status(
        client_with_reply_hook(award_points), room_code, "Racer", connected=True
    )

    assert award_points.fired
    stored = await room_service.get_player(real_redis_client, room_code, "Racer")
    assert stored is not None
    assert (stored.score, stored.connected) == (40, True)
    assert updated == stored


async def test_simultaneous_score_updates_for_one_player_all_count(
    real_redis_client: RedisClient,
) -> None:
    """Twenty score updates at once all land, each on top of the one before it."""
    room_code = "RCON"
    await room_service.add_player(real_redis_client, room_code, Player(nickname="Racer"))

    updated = await asyncio.gather(
        *(
            room_service.update_player_score(real_redis_client, room_code, "Racer", 10)
            for _ in range(20)
        )
    )

    stored = await room_service.get_player(real_redis_client, room_code, "Racer")
    assert stored is not None
    assert stored.score == 200
    assert sorted(player.score for player in updated if player) == list(range(10, 201, 10))


async def test_add_player_never_leaves_players_without_ttl(
    real_redis: redis.Redis,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    """The hash has a TTL at every reply during add_player, wherever a cancelled caller stops."""
    room_code = "ATTL"
    players_key = f"room:{room_code}:players"
    ttls_seen: list[int] = []

    async def record_ttl(_command: Command) -> None:
        ttls_seen.append(await real_redis.ttl(players_key))

    await room_service.add_player(
        client_with_reply_hook(record_ttl), room_code, Player(nickname="Joiner")
    )

    assert ttls_seen, "the hook saw no replies"
    assert -1 not in ttls_seen
    assert await real_redis.ttl(players_key) > 0


async def test_score_update_whose_exec_reply_is_lost_is_applied_once(
    real_redis_client: RedisClient,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    """A lost EXEC reply fails the update instead of retrying a write that already ran."""
    room_code = "RLST"
    await room_service.add_player(real_redis_client, room_code, Player(nickname="Racer"))
    lose_exec_reply = LoseExecReply()

    with pytest.raises(RedisTimeoutError):
        await room_service.update_player_score(
            client_with_reply_hook(lose_exec_reply), room_code, "Racer", 10
        )

    assert lose_exec_reply.fired
    stored = await room_service.get_player(real_redis_client, room_code, "Racer")
    assert stored is not None
    assert stored.score == 10


async def test_guess_whose_exec_reply_is_lost_is_not_reported_as_a_repeat(
    real_redis_client: RedisClient,
    client_with_reply_hook: Callable[[AfterReply], RedisClient],
) -> None:
    """A lost EXEC reply fails the guess, rather than a retry calling it ALREADY_GUESSED."""
    room_code = "RGLS"
    await _start_accepting_round(real_redis_client, room_code)
    lose_exec_reply = LoseExecReply()

    with pytest.raises(RedisTimeoutError):
        await room_service.record_guess(
            client_with_reply_hook(lose_exec_reply),
            room_code,
            PlayerGuess(nickname="Late", guess="KJFK"),
        )

    assert lose_exec_reply.fired
    stored = await room_service.get_round_data(real_redis_client, room_code)
    assert stored is not None
    assert list(stored.guesses) == ["Late"]

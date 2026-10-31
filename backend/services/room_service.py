import logging
import time
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Dict

from redis.asyncio.client import Pipeline
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from redis.exceptions import WatchError

from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import PlayerGuess, RoundData, RoundStateEnum, SoloSelectionContext
from backend.utils.airport_db import resolve_airport
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

ROUND_TTL_SECONDS = 3600


class GuessOutcome(StrEnum):
    """Result of trying to record a player's guess."""

    RECORDED = "recorded"
    NO_ROUND = "no_round"
    NOT_ACCEPTING = "not_accepting"
    ALREADY_GUESSED = "already_guessed"
    UNKNOWN_AIRPORT = "unknown_airport"


async def get_player(redis: RedisClient, room_code: str, nickname: str) -> Player | None:
    """Get a player from a room by nickname.

    Args:
        redis: Redis client instance
        room_code: Room code to get player from
        nickname: Player nickname to get

    Returns:
        Player object if found, None otherwise
    """
    players_key = f"room:{room_code}:players"
    return await redis.hget_model(players_key, nickname, Player)


async def add_player(redis: RedisClient, room_code: str, player: Player) -> Player:
    """Add or update a player in a room.

    Args:
        redis: Redis client instance
        room_code: Room code to add player to
        player: Player object to add/update

    Returns:
        The added/updated Player object
    """
    players_key = f"room:{room_code}:players"
    room_ttl = 3600  # 1 hour

    # One transaction, so the hash never exists without its TTL, even if this task is cancelled.
    async with await redis.get_connection() as conn, conn.pipeline(transaction=True) as pipe:
        pipe.hset(players_key, player.nickname, player.model_dump_json())
        pipe.expire(players_key, room_ttl)
        await pipe.execute()
    return player


async def create_solo_room_instance(
    nickname: str, redis_client: RedisClient
) -> tuple[str, RoomMeta]:
    """Create an isolated solo room and return its code and metadata."""
    solo_code = f"solo:{uuid.uuid4().hex[:8]}"
    meta = RoomMeta(
        mode=ScoringMode.EXACT,
        round_timeout_seconds=0,
        host_nickname=nickname,
        is_solo=True,
    )
    meta_key = f"room:{solo_code}:meta"
    await redis_client.set_json(meta_key, meta, expire_seconds=3600)
    # Add the solo player as the only player in the room
    await add_player(redis_client, solo_code, Player(nickname=nickname))
    return solo_code, meta


async def _execute_watched(pipe: Pipeline) -> None:
    """Execute a WATCHed transaction; a WatchError from it means a watched key changed.

    While a key is watched, redis-py also turns a lost connection or a reply timeout into a
    WatchError, raised while handling that error (a changed key's is raised ``from None``).
    EXEC may already have run then, and retrying could apply the write twice, so the
    connection error is raised instead and the caller's retry loop lets it through.
    """
    try:
        await pipe.execute()
    except WatchError as e:
        lost = e.__context__
        if not e.__suppress_context__ and isinstance(
            lost, (RedisConnectionError, RedisTimeoutError)
        ):
            raise lost from None
        raise


async def _update_player(
    redis: RedisClient, room_code: str, nickname: str, change: Callable[[Player], None]
) -> Player | None:
    """Apply ``change`` to a stored player and return the player as stored.

    The read-change-write runs under WATCH/MULTI on the players hash and retries when another
    writer changes the hash in between. The write only lands on the hash it read, so it cannot
    recreate a hash that was deleted or expired (it would have no TTL, and production Redis
    never evicts it), bring back a removed player, or overwrite a concurrent change.

    Returns None, without writing, if the player is not in the room or cannot be parsed.
    """
    players_key = f"room:{room_code}:players"
    async with await redis.get_connection() as conn, conn.pipeline(transaction=True) as pipe:
        while True:
            try:
                await pipe.watch(players_key)
                player_json = await pipe.hget(players_key, nickname)
                if player_json is None:
                    return None
                try:
                    player = Player.model_validate_json(player_json)
                except ValueError as e:
                    logger.error(f"Error deserializing player '{nickname}' in {players_key}: {e}")
                    return None

                change(player)
                pipe.multi()
                pipe.hset(players_key, nickname, player.model_dump_json())
                await _execute_watched(pipe)
                return player
            except WatchError:
                logger.debug(
                    "Players of room %s changed while updating %s; retrying.", room_code, nickname
                )


async def update_player_status(
    redis: RedisClient, room_code: str, nickname: str, connected: bool
) -> Player | None:
    """Sets a player's connection status and returns the updated player."""

    def set_status(player: Player) -> None:
        player.connected = connected
        player.last_seen_ts = time.time()

    try:
        player = await _update_player(redis, room_code, nickname, set_status)
    except Exception as e:
        logger.error(
            f"Failed to update status for player '{nickname}' in room '{room_code}': {e}",
            exc_info=True,
        )
        raise  # Re-raise to signal failure
    if player is None:
        logger.warning(
            f"Attempted to update status for non-existent player '{nickname}' "
            f"in room '{room_code}'."
        )
        return None
    logger.debug(
        f"Updated player '{nickname}' status in room '{room_code}' to connected={connected}."
    )
    return player


async def update_player_score(
    redis: RedisClient, room_code: str, nickname: str, score_change: int
) -> Player | None:
    """Adds score_change to a player's score and returns the updated player."""

    def add_score(player: Player) -> None:
        player.score += score_change
        player.last_seen_ts = time.time()  # Update activity timestamp

    try:
        player = await _update_player(redis, room_code, nickname, add_score)
    except Exception as e:
        logger.error(
            f"Failed to update score for player '{nickname}' in room '{room_code}': {e}",
            exc_info=True,
        )
        raise  # Re-raise
    if player is None:
        logger.warning(
            f"Attempted to update score for non-existent player '{nickname}' in room '{room_code}'."
        )
        return None
    logger.info(
        f"Updated player '{nickname}' score by {score_change} to "
        f"{player.score} in room '{room_code}'."
    )
    return player


async def get_all_players(redis: RedisClient, room_code: str) -> Dict[str, Player]:
    """Get all players in a room.

    Args:
        redis: Redis client instance
        room_code: Room code to get players from

    Returns:
        Dictionary of nickname -> Player for all players in room
    """
    players_key = f"room:{room_code}:players"
    return await redis.hgetall_models(players_key, Player)


# --- Solo Selection Context Helpers --- #


async def set_solo_player_selection_context(
    redis: RedisClient, room_code: str, context: SoloSelectionContext
) -> bool:
    key = f"room:{room_code}:solo_context"
    return await redis.set_json(key, context, expire_seconds=3600)


async def get_solo_player_selection_context(
    redis: RedisClient, room_code: str
) -> SoloSelectionContext | None:
    key = f"room:{room_code}:solo_context"
    return await redis.get_model(key, SoloSelectionContext)


async def clear_solo_player_selection_context(redis: RedisClient, room_code: str) -> None:
    key = f"room:{room_code}:solo_context"
    await redis.delete(key)


# --- Room Metadata Helpers --- #


async def get_room_meta(redis: RedisClient, room_code: str) -> RoomMeta | None:
    """Retrieve the RoomMeta data for a given room code."""
    meta_key = f"room:{room_code}:meta"
    try:
        return await redis.get_model(meta_key, RoomMeta)
    except Exception as e:
        logger.error(f"Failed to get or parse RoomMeta for room '{room_code}': {e}", exc_info=True)
        raise  # Re-raise to indicate failure


async def set_room_meta(redis: RedisClient, room_code: str, room_meta: RoomMeta) -> bool:
    """Set the RoomMeta data for a given room code, applying room TTL.

    Args:
        redis: Redis client instance.
        room_code: The four-letter room code.
        room_meta: The RoomMeta instance to persist.

    Returns:
        True if the underlying Redis *SET* succeeded, False otherwise.
    """
    meta_key = f"room:{room_code}:meta"
    room_ttl_seconds = 3600  # TODO: derive from settings later
    try:
        success: bool = await redis.set_json(meta_key, room_meta, expire_seconds=room_ttl_seconds)
        if success:
            logger.debug("Set RoomMeta for room '%s'.", room_code)
        else:
            logger.error("Redis SET command failed for RoomMeta key: %s", meta_key)
        return success
    except Exception as e:
        logger.error("Failed to set RoomMeta for room '%s': %s", room_code, e, exc_info=True)
        raise


# --- Round Data Helpers --- #


async def get_round_data(redis: RedisClient, room_code: str) -> RoundData | None:
    """Retrieve the current round data for a room.

    Returns RoundData or None if key doesn't exist.
    If the key exists but fails to parse, raises an exception.
    """
    round_key = f"room:{room_code}:round"
    try:
        round_data = await redis.get_model(round_key, RoundData)
        return round_data
    except Exception as e:
        logger.error(
            f"Failed to get or parse round data for room '{room_code}': {e}", exc_info=True
        )
        # Depending on desired behavior, either return None or re-raise
        # Returning None might mask parsing errors vs. non-existence
        raise


async def set_round_data(redis: RedisClient, room_code: str, round_data: RoundData) -> bool:
    """Set the round data for a room, applying room TTL.

    Overwrites existing round data.
    """
    round_key = f"room:{room_code}:round"
    try:
        logger.info(
            f"SETTING ROUND DATA for key {round_key}. Current round data object (Python): "
            f"{round_data.model_dump(mode='python')}"
        )
        logger.info(
            f"SETTING ROUND DATA for key {round_key}. Current round data object (JSON Str): "
            f"{round_data.model_dump_json(indent=2)}"
        )
        success = await redis.set_json(round_key, round_data, expire_seconds=ROUND_TTL_SECONDS)
        logger.info(f"Redis SET command for {round_key} returned: {success}")
        if success:
            logger.debug(f"Set round data for room '{room_code}' to state {round_data.state}")
        else:
            logger.error(f"Redis SET command failed for round data key: {round_key}")
        return success  # Return the success status
    except Exception as e:
        logger.error(f"Failed to set round data for room '{room_code}': {e}", exc_info=True)
        raise


async def record_guess(
    redis: RedisClient, room_code: str, guess: PlayerGuess
) -> tuple[GuessOutcome, RoundData | None]:
    """Add ``guess`` to the room's round without losing guesses written concurrently.

    The read-check-write runs under WATCH/MULTI on the round key and retries when another
    writer changes the round in between, so two players guessing at the same moment both
    end up in the stored round.

    Returns the outcome and the round as stored after this call (``None`` if the room has
    no round). A guess is only recorded while the round accepts guesses, the player has
    not guessed yet, and the code is in the airport dataset. The round-state and duplicate
    checks come first, so their outcomes take precedence over ``UNKNOWN_AIRPORT``.
    """
    round_key = f"room:{room_code}:round"
    async with await redis.get_connection() as conn, conn.pipeline(transaction=True) as pipe:
        while True:
            try:
                await pipe.watch(round_key)
                round_json = await pipe.get(round_key)
                if round_json is None:
                    return GuessOutcome.NO_ROUND, None
                round_data = RoundData.model_validate_json(round_json)
                if round_data.state != RoundStateEnum.ACCEPTING_GUESSES:
                    return GuessOutcome.NOT_ACCEPTING, round_data
                if guess.nickname in round_data.guesses:
                    return GuessOutcome.ALREADY_GUESSED, round_data
                if resolve_airport(guess.guess) is None:
                    return GuessOutcome.UNKNOWN_AIRPORT, round_data

                round_data.guesses = {**round_data.guesses, guess.nickname: guess}
                pipe.multi()
                pipe.set(round_key, round_data.model_dump_json(), ex=ROUND_TTL_SECONDS)
                await _execute_watched(pipe)
                return GuessOutcome.RECORDED, round_data
            except WatchError:
                logger.debug("Round %s changed while recording a guess; retrying.", room_code)


async def initialize_round_data(redis: RedisClient, room_code: str) -> RoundData:
    """Initializes round data if it doesn't exist, otherwise returns existing.

    Useful when a room is created or game starts.
    """
    existing_data = await get_round_data(redis, room_code)
    if existing_data:
        return existing_data

    logger.info(f"Initializing round data for room '{room_code}'.")
    new_round_data = RoundData()  # Creates with default WAITING_FOR_SELECTION state
    await set_round_data(redis, room_code, new_round_data)
    return new_round_data


async def delete_room(redis: RedisClient, room_code: str) -> None:
    """Delete all Redis keys associated with a game room.

    Args:
        redis: Redis client wrapper.
        room_code: 4-letter room code.

    Raises:
        Exception: Propagates unexpected Redis errors.
    """
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"
    round_key = f"room:{room_code}:round"
    solo_context_key = f"room:{room_code}:solo_context"

    try:
        async with await redis.get_connection() as conn:
            await conn.delete(
                meta_key,
                players_key,
                round_key,
                solo_context_key,
            )  # type: ignore[attr-defined]
        logger.info(
            "Deleted room %s (keys: %s, %s, %s, %s)",
            room_code,
            meta_key,
            players_key,
            round_key,
            solo_context_key,
        )
    except Exception as exc:  # noqa: BLE001 – bubble up after logging
        logger.error("Failed to delete room %s: %s", room_code, exc, exc_info=True)
        raise

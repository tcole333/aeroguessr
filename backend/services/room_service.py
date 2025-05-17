import logging
import time
from typing import Dict

from backend.schemas.core import Player, RoomMeta
from backend.schemas.game import RoundData
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)


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

    # Store player data using the wrapper method
    await redis.hset_model(players_key, player.nickname, player)
    await redis.expire(players_key, room_ttl)
    return player


async def update_player_status(
    redis: RedisClient, room_code: str, nickname: str, connected: bool
) -> Player | None:
    """Adds score_change to a player's score and returns the updated player."""
    players_key = f"room:{room_code}:players"
    player = await redis.hget_model(players_key, nickname, Player)
    if player:
        player.connected = connected
        player.last_seen_ts = time.time()
        try:
            await redis.hset_model(players_key, nickname, player)
            logger.debug(
                f"Updated player '{nickname}' status in room '{room_code}' "
                f"to connected={connected}."
            )
            return player
        except Exception as e:
            logger.error(
                f"Failed to update status for player '{nickname}' in room '{room_code}': {e}",
                exc_info=True,
            )
            raise  # Re-raise to signal failure
    else:
        logger.warning(
            f"Attempted to update status for non-existent player '{nickname}' "
            f"in room '{room_code}'."
        )
        return None


async def update_player_score(
    redis: RedisClient, room_code: str, nickname: str, score_change: int
) -> Player | None:
    """Adds score_change to a player's score and returns the updated player."""
    players_key = f"room:{room_code}:players"
    player = await redis.hget_model(players_key, nickname, Player)
    if player:
        player.score += score_change
        player.last_seen_ts = time.time()  # Update activity timestamp
        try:
            await redis.hset_model(players_key, nickname, player)
            logger.info(
                f"Updated player '{nickname}' score by {score_change} to "
                f"{player.score} in room '{room_code}'."
            )
            return player
        except Exception as e:
            logger.error(
                f"Failed to update score for player '{nickname}' in room '{room_code}': {e}",
                exc_info=True,
            )
            raise  # Re-raise
    else:
        logger.warning(
            f"Attempted to update score for non-existent player '{nickname}' in room '{room_code}'."
        )
        return None


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


async def remove_player(redis: RedisClient, room_code: str, nickname: str) -> bool:
    """Remove a player from the room's player hash. Returns True if deleted."""
    players_key = f"room:{room_code}:players"
    try:
        deleted_count = await redis.hdel(players_key, nickname)
        if deleted_count > 0:
            logger.info(f"Removed player '{nickname}' from room '{room_code}'.")
            return True
        else:
            logger.warning(
                f"Attempted to remove non-existent player '{nickname}' from room '{room_code}'."
            )
            return False
    except Exception as e:
        logger.error(
            f"Failed to remove player '{nickname}' from room '{room_code}': {e}",
            exc_info=True,
        )
        raise  # Re-raise


# --- Room Metadata Helpers --- #


# TODO: Add functions for managing room metadata (get_room_meta, set_room_meta)
# Example:
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
    room_ttl_seconds = 3600  # Consider getting this from config or RoomMeta
    try:
        logger.info(
            f"SETTING ROUND DATA for key {round_key}. Current round data object (Python): "
            f"{round_data.model_dump(mode='python')}"
        )
        logger.info(
            f"SETTING ROUND DATA for key {round_key}. Current round data object (JSON Str): "
            f"{round_data.model_dump_json(indent=2)}"
        )
        success = await redis.set_json(round_key, round_data, expire_seconds=room_ttl_seconds)
        logger.info(f"Redis SET command for {round_key} returned: {success}")
        if success:
            logger.debug(f"Set round data for room '{room_code}' to state {round_data.state}")
        else:
            logger.error(f"Redis SET command failed for round data key: {round_key}")
        return success  # Return the success status
    except Exception as e:
        logger.error(f"Failed to set round data for room '{room_code}': {e}", exc_info=True)
        raise


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


# TODO: Add functions for managing round state (get_round_data, set_round_data)


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

    try:
        async with await redis.get_connection() as conn:
            await conn.delete(meta_key, players_key, round_key)  # type: ignore[attr-defined]
        logger.info(
            "Deleted room %s (keys: %s, %s, %s)", room_code, meta_key, players_key, round_key
        )
    except Exception as exc:  # noqa: BLE001 – bubble up after logging
        logger.error("Failed to delete room %s: %s", room_code, exc, exc_info=True)
        raise

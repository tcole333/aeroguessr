import asyncio
import json
import logging
import os
import random
import time
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from backend.ingest.main import PlaneState
from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import PlayerGuess, RoundResultDetail, RoundStateEnum
from backend.schemas.room import (
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinRequest,
    RoomJoinResponse,
    RoomState,
    generate_room_code,
)
from backend.schemas.ws import (
    ErrorCode,
    ErrorPayload,
    FullRoomState,
    GuessPayload,
    NewHostPayload,
    PingPongPayload,
    PlayerJoinedPayload,
    PlayerLeftPayload,
    RoundResultPayload,
    RoundStartPayload,
    SelectPlanePayload,
    WSMessage,
    WSMessageType,
)
from backend.services import room_service, scoring
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

# Environment Variable for Host Claim Window (seconds)
_DEFAULT_HOST_CLAIM_WINDOW_SECONDS = 120
HOST_DISCONNECT_CLAIM_WINDOW_SECONDS = int(
    os.getenv("HOST_DISCONNECT_CLAIM_WINDOW_SECONDS", _DEFAULT_HOST_CLAIM_WINDOW_SECONDS)
)

# Heartbeat constants
PING_INTERVAL_SECONDS = 10  # Send a ping every 10 seconds
MAX_MISSED_PINGS = 3  # Disconnect after 3 missed pongs (e.g., 30 seconds total timeout)

logger = logging.getLogger(__name__)

# <<< TEMPORARY DEBUGGING >>>
logger.setLevel(logging.DEBUG)
# <<<<<<<<<<<<<<<<<<<<<<<<<<<

# --- Global State / Dependencies --- #
# Initialize outside lifespan for potential direct access if needed,
# but manage connections within lifespan.
# TODO: Review if global instances are the best approach vs. dependency injection.
redis_client_global = RedisClient()
# Use the same ConnectionManager instance used by room WebSocket endpoints to
# ensure background broadcast tasks and routes share connection tracking.
# This avoids issues where plane `delta` messages are prepared but not delivered
# because the broadcast task held a separate, empty manager instance.
# Import after rooms to avoid circular import problems.
manager = ConnectionManager()


# Dependency function to get Redis client
# (Could be moved to a dedicated deps.py file later)
async def get_redis() -> RedisClient:
    # This assumes RedisClient can be instantiated directly.
    # If it needs setup (like connecting pool), that should happen elsewhere
    # (e.g., FastAPI lifespan events) and this function would yield the client.
    # For now, direct instantiation works with the current RedisClient structure.
    return redis_client_global


# Dependency function to get the global ConnectionManager instance
def get_connection_manager() -> ConnectionManager:
    return manager


# Remove in-memory stubs
# rooms_db: dict[str, RoomMeta] = {}
# players_db: dict[str, dict[str, Player]] = {} # {room_code: {nickname: Player}}

router = APIRouter(
    prefix="/api/v0/rooms",
    tags=["rooms"],  # Tag for OpenAPI documentation grouping
)


@router.post(
    "",
    response_model=RoomCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new game room",
    description=(
        "Creates a new game room with a unique code and returns the code "
        "and WebSocket URL for the host."
    ),
)
async def create_room(
    request: Request,
    room_data: RoomCreateRequest,
    response: Response,
    redis: RedisClient = Depends(get_redis),
) -> RoomCreateResponse:
    """
    Creates a new game room and registers the host in Redis.

    Args:
        request: The incoming request object (used to build the WS URL).
        room_data: Data for the new room including host nickname, mode, and timeout.
        response: The outgoing response object (used to set Location header).
        redis: Injected RedisClient instance.

    Returns:
        The room code and WebSocket URL for the host.

    Raises:
        HTTPException: If a unique room code cannot be generated after several tries.
    """
    # 1. Generate unique room code (check for collisions, though unlikely)
    room_code = generate_room_code()

    max_retries = 5
    for _ in range(max_retries):
        room_code = generate_room_code()
        meta_key = f"room:{room_code}:meta"
        if not await redis.exists(meta_key):
            break  # Found a unique code
    else:
        # This is very unlikely with 4-char codes, but handle defensively
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate a unique room code.",
        )

    # Define keys based on PRD schema
    # players_key = f"room:{room_code}:players"
    room_ttl = 3600  # 1 hour

    # Create initial room metadata
    new_room_meta = RoomMeta(
        mode=room_data.mode,
        round_timeout_seconds=room_data.round_timeout_seconds,
        host_nickname=room_data.host_nickname,
        # created_ts is handled by default_factory
    )

    # Create initial player data for the host
    host_player = Player(
        nickname=room_data.host_nickname,
        connected=False,  # Connects via WS later
        # last_seen_ts will be updated on connect/activity
    )

    try:
        # Store room metadata (Keep direct Redis call for non-player meta)
        await redis.set_json(meta_key, new_room_meta, expire_seconds=room_ttl)

        # Use room_service to add the host player
        await room_service.add_player(redis=redis, room_code=room_code, player=host_player)
        # TTL for the players hash is handled within add_player

    except Exception as e:
        # Basic error handling, consider more specific exceptions
        # Potentially try to clean up partially created keys if needed
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create room in Redis: {e}",
        ) from e

    # Construct WebSocket URL dynamically
    # Assuming the API is served at the root, adjust if behind a proxy with path prefix
    # Use request.base_url to handle http/https correctly
    base_ws_url = str(request.base_url).replace("http", "ws", 1)
    ws_url = f"{base_ws_url}ws/{room_code}/{room_data.host_nickname}"

    # Set Location header (as specified in PRD)
    response.headers["Location"] = ws_url

    return RoomCreateResponse(room_code=room_code, ws_url=ws_url)


@router.post(
    "/{room_code}/join",
    response_model=RoomJoinResponse,
    status_code=status.HTTP_200_OK,
    summary="Join an existing game room",
    description=(
        "Allows a player to join a room using a code and nickname. "
        "Checks for room existence and nickname uniqueness."
    ),
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Room not found"},
        status.HTTP_409_CONFLICT: {"description": "Nickname already taken in this room"},
    },
)
async def join_room(
    request: Request,
    room_code: str,
    join_data: RoomJoinRequest,
    redis: RedisClient = Depends(get_redis),
) -> RoomJoinResponse:
    """
    Allows a player to join an existing room.

    Args:
        request: The incoming request object.
        room_code: The 4-letter code of the room to join.
        join_data: Data containing the player's desired nickname.
        redis: Injected RedisClient instance.

    Returns:
        The WebSocket URL for the player to connect to.

    Raises:
        HTTPException (404): If the room_code does not correspond to an active room.
        HTTPException (409): If the chosen nickname is already in use in the room.
        HTTPException (500): If there is an error interacting with Redis.
    """
    # 1. Check if room exists (check meta key)
    meta_key = f"room:{room_code}:meta"
    room_ttl = 3600  # 1 hour

    if not await redis.exists(meta_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Room '{room_code}' not found."
        )

    # 2. Check if nickname is already taken in this room
    # Use room_service to check for existing player
    existing_player = await room_service.get_player(
        redis=redis, room_code=room_code, nickname=join_data.nickname
    )
    if existing_player:
        # TODO: Allow rejoining if nickname matches an existing *disconnected* player?
        # For now, strictly unique active nicknames.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Nickname '{join_data.nickname}' is already taken in room '{room_code}'.",
        )

    # 3. Create and add the new player
    new_player = Player(
        nickname=join_data.nickname,
        connected=False,  # Will connect via WS
    )

    try:
        # Use room_service to add the new player
        await room_service.add_player(redis=redis, room_code=room_code, player=new_player)

        # 4. Refresh TTLs to keep room alive (Only meta TTL needs explicit refresh here)
        # Player hash TTL is handled by add_player
        await redis.expire(meta_key, room_ttl)
        # await redis.expire(players_key, room_ttl) # No longer needed

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add player to room in Redis: {e}",
        ) from e

    # 5. Construct WebSocket URL
    base_ws_url = str(request.base_url).replace("http", "ws", 1)
    ws_url = f"{base_ws_url}ws/{room_code}/{join_data.nickname}"

    return RoomJoinResponse(ws_url=ws_url)


@router.websocket("/ws/{room_code}/{nickname}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    nickname: str,
    redis: RedisClient = Depends(get_redis),
    conn_manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    """Main WebSocket endpoint for handling game room communication."""
    logger.info(f"WS connection attempt: room='{room_code}', nick='{nickname}'.")

    # --- Pre-Connection Checks & Setup ---
    # 1. Check if room exists
    meta_key = f"room:{room_code}:meta"
    if not await redis.exists(meta_key):
        logger.warning(f"WS connection rejected: Room '{room_code}' not found.")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Check if nickname is valid (exists in the room's player list)
    player_data = await room_service.get_player(redis, room_code, nickname)
    if not player_data:
        logger.warning(
            f"WS connection rejected: Nickname '{nickname}' not found in room '{room_code}'."
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 3. Check if nickname is already connected (prevent double connections)
    # Check if the nickname exists *within the connection manager* for this room
    existing_connection_state = conn_manager.get_connection_state(room_code, nickname)
    if (
        existing_connection_state
        and existing_connection_state.websocket.client_state == WebSocketState.CONNECTED
    ):
        logger.warning(
            f"WS connection rejected: Nickname '{nickname}' "
            f"already connected in room '{room_code}'."
        )
        # Send error to the *existing* connection? Might be complex.
        # For now, reject the new connection attempt.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # --- Accept Connection & Initial State --- #
    await conn_manager.connect(websocket, room_code, nickname)
    logger.info(f"Player '{nickname}' successfully connected via WS to room '{room_code}'.")

    # Update player status in Redis
    try:
        await room_service.update_player_status(redis, room_code, nickname, connected=True)
    except Exception as e:
        logger.error(
            f"Failed to update player status for {nickname} in {room_code}: {e}", exc_info=True
        )
        # Continue connection attempt, but log error

    # --- Send Initial State Sync --- #
    try:
        # Gather current room state (meta, players, etc.)
        room_meta_instance = await room_service.get_room_meta(redis, room_code)
        all_player_instances = await room_service.get_all_players(redis, room_code)

        # Manually convert to dictionaries before FullRoomState initialization
        room_meta_dict = room_meta_instance.model_dump(mode="json") if room_meta_instance else None
        all_players_dict = {
            nick: player.model_dump(mode="json") for nick, player in all_player_instances.items()
        }

        # Construct FullRoomState payload using dictionaries
        state_payload_model = FullRoomState(room_meta=room_meta_dict, players=all_players_dict)

        ws_payload_dict = state_payload_model.model_dump(mode="json")
        state_sync_msg = WSMessage(type=WSMessageType.STATE_SYNC, payload=ws_payload_dict)
        await conn_manager.send_personal_message(state_sync_msg.model_dump(mode="json"), websocket)
        logger.debug(f"Sent STATE_SYNC to {nickname} in {room_code}.")
    except WebSocketDisconnect:
        logger.warning(f"WS disconnected immediately after connect for {nickname}. Cleaning up.")
        conn_manager.disconnect(room_code, nickname)
        await room_service.update_player_status(redis, room_code, nickname, connected=False)
        return  # Exit if initial send fails
    except Exception as e:
        logger.error(f"Error sending initial state sync to {nickname}: {e}", exc_info=True)
        # Proceed, but initial state might be missing for this client

    # --- Broadcast Player Joined --- #
    # Exclude self from broadcast
    join_payload_model = PlayerJoinedPayload(nickname=nickname)
    # Ensure the inner payload is dumped to a dict before being assigned to WSMessage
    join_msg = WSMessage(type=WSMessageType.PLAYER_JOINED, payload=join_payload_model.model_dump())
    broadcast_data_join = join_msg.model_dump()  # Now this should have the payload as a dict
    logger.debug(f"Broadcasting PLAYER_JOINED with data: {broadcast_data_join}")
    await conn_manager.broadcast(broadcast_data_join, room_code, exclude_nickname=nickname)

    # --- Game Logic / Host State Setup --- #
    # Fetch current round state AFTER sending initial sync
    current_round_data = await room_service.get_round_data(redis, room_code)  # noqa: F841
    room_meta_for_logic = await room_service.get_room_meta(redis, room_code)
    is_host = room_meta_for_logic and room_meta_for_logic.host_nickname == nickname

    # Timer tasks (need to be managed)
    host_disconnect_check_task: Optional[asyncio.Task] = None
    auto_transfer_host_task: Optional[asyncio.Task] = None
    round_timer_task: Optional[asyncio.Task] = None

    # Host disconnect tracking
    host_disconnected_at: Optional[float] = None
    claim_host_allowed: bool = False

    # --- Helper Functions (defined within endpoint scope for context access) --- #

    async def _handle_host_disconnect() -> None:
        """Records the host disconnect time in Redis."""
        nonlocal \
            host_disconnected_at, \
            claim_host_allowed, \
            host_disconnect_check_task, \
            auto_transfer_host_task
        logger.warning(
            f"Host {nickname} disconnected from room {room_code}. Recording disconnect time."
        )

        # Fetch current meta
        current_meta = await room_service.get_room_meta(redis, room_code)
        if not current_meta:
            logger.error(f"Cannot handle host disconnect: Room {room_code} meta not found.")
            return
        if current_meta.host_nickname != nickname:
            logger.error(
                f"Non-host {nickname} triggered _handle_host_disconnect? "
                f"Meta host: {current_meta.host_nickname}"
            )
            return  # Should not happen

        # Record disconnect time
        current_meta.host_disconnected_ts = time.time()
        success = await room_service.set_room_meta(redis, room_code, current_meta)
        if not success:
            logger.error(f"Failed to save host disconnect timestamp for room {room_code}.")
            # Continue anyway to start auto-transfer timer?

        # --- Start Auto-Transfer Timer (Keep for now) --- #
        if auto_transfer_host_task and not auto_transfer_host_task.done():
            auto_transfer_host_task.cancel()

        async def _auto_transfer_host() -> None:
            await asyncio.sleep(300)  # 5 minutes
            logger.warning(
                f"Auto-transfer timeout (5 min) reached for room {room_code}. Checking state."
            )
            current_meta_check = await room_service.get_room_meta(redis, room_code)
            if not current_meta_check or current_meta_check.host_disconnected_ts is None:
                logger.info(
                    f"Auto-transfer aborted for room {room_code}: Host reconnected or room gone."
                )
                return
            # Check original host nickname matches who disconnected, not current claimer
            # This check might be redundant if host_disconnected_ts is the source of truth
            # if current_meta_check.host_nickname == nickname:
            #      logger.info(f"Auto-transfer aborted for room {room_code}: Original host
            # ({nickname}) reconnected?)")
            #      return # Should have cleared timestamp if reconnected

            # Select a new host randomly from connected players
            all_players = await room_service.get_all_players(redis, room_code)
            # Ensure we don't select the disconnected host (nickname is the one who disconnected)
            connected_players = [
                p for p in all_players.values() if p.connected and p.nickname != nickname
            ]
            if not connected_players:
                logger.warning(
                    f"Cannot auto-transfer host in room {room_code}: No other connected players."
                )
                return

            new_host = random.choice(connected_players)
            current_meta_check.host_nickname = new_host.nickname
            current_meta_check.host_disconnected_ts = None  # Clear disconnect time
            await room_service.set_room_meta(redis, room_code, current_meta_check)
            logger.info(f"Auto-transferring host to {new_host.nickname} in room {room_code}.")

            # Broadcast newHost message
            new_host_payload = NewHostPayload(nickname=new_host.nickname)
            new_host_message = WSMessage(type="newHost", payload=new_host_payload.model_dump())
            await conn_manager.broadcast(new_host_message.model_dump(), room_code)

        auto_transfer_host_task = asyncio.create_task(
            _auto_transfer_host(), name=f"auto_transfer_{room_code}"
        )
        conn_manager.add_task(auto_transfer_host_task)  # Add task for tracking
        # Callback to remove task from set when done/cancelled
        auto_transfer_host_task.add_done_callback(conn_manager._remove_task_from_set)

    async def _clear_host_disconnect_state() -> None:
        """Clears host disconnect timestamp if the host reconnects."""
        nonlocal \
            host_disconnected_at, \
            claim_host_allowed, \
            host_disconnect_check_task, \
            auto_transfer_host_task

        # Fetch current meta
        current_meta = await room_service.get_room_meta(redis, room_code)
        if not current_meta:
            logger.error(f"Cannot clear host disconnect state: Room {room_code} meta not found.")
            return
        if current_meta.host_nickname != nickname:
            # This function is called on *reconnect*, so nickname should be the host
            logger.warning(f"_clear_host_disconnect_state called by non-host {nickname}? Ignoring.")
            return

        if current_meta.host_disconnected_ts is not None:
            logger.info(f"Host {nickname} reconnected. Clearing disconnect timestamp.")
            current_meta.host_disconnected_ts = None
            success = await room_service.set_room_meta(redis, room_code, current_meta)
            if not success:
                logger.error(f"Failed to clear host disconnect timestamp for room {room_code}.")

        # Cancel auto-transfer timer if host reconnects
        if auto_transfer_host_task and not auto_transfer_host_task.done():
            logger.info(f"Host {nickname} reconnected. Cancelling auto-transfer timer.")
            auto_transfer_host_task.cancel()
            auto_transfer_host_task = None

    async def _end_round(initiator: str = "timer") -> None:
        """Handles scoring, result broadcast, and state transition at round end."""
        nonlocal round_timer_task
        logger.info(f"Attempting to end round for room {room_code}, initiated by {initiator}.")

        # Prevent multiple simultaneous ends (e.g., timer and last guess)
        # This requires careful state management or locking if truly concurrent
        # For now, assume get/set is fast enough for typical race conditions
        round_data = await room_service.get_round_data(redis, room_code)
        if not round_data or round_data.state != RoundStateEnum.ACCEPTING_GUESSES:
            logger.warning(
                (
                    f"_end_round called for room {room_code} but state is "
                    f"{round_data.state if round_data else 'N/A'}. Ignoring."
                )
            )
            # Cancel timer if it's still running but state changed unexpectedly
            if round_timer_task and not round_timer_task.done():
                round_timer_task.cancel()
            return

        # Cancel the timer task if it exists and isn't the initiator
        if initiator != "timer" and round_timer_task and not round_timer_task.done():
            logger.debug(f"Round ended early by {initiator}, cancelling timer task.")
            round_timer_task.cancel()
            round_timer_task = None  # Clear reference

        # --- Scoring --- #
        logger.info(
            f"Ending round {round_data.round_number} for room {room_code}. Calculating scores."
        )
        results: List[RoundResultDetail] = []
        all_players = await room_service.get_all_players(redis, room_code)
        correct_code = round_data.correct_airport_code
        room_meta_local = await room_service.get_room_meta(
            redis, room_code
        )  # Fetch fresh meta for scoring mode

        if not room_meta_local:
            logger.error(f"Cannot end round: RoomMeta not found for {room_code}")
            # Transition to waiting? Or handle error differently?
            round_data.state = RoundStateEnum.WAITING_FOR_SELECTION
            await room_service.set_round_data(redis, room_code, round_data)
            return

        if not correct_code:
            logger.error(
                (
                    f"Cannot end round: Correct airport code not set for "
                    f"round {round_data.round_number} in {room_code}"
                )
            )
            round_data.state = RoundStateEnum.WAITING_FOR_SELECTION
            await room_service.set_round_data(redis, room_code, round_data)
            return

        scoring_mode = room_meta_local.mode
        updated_scores_delta = {}  # Store score changes for delta message

        for p_nick, player_data in all_players.items():
            # Only score connected players who made a guess for this round
            player_guess: Optional[PlayerGuess] = round_data.guesses.get(p_nick)
            score_awarded = 0
            guessed_code = None

            if player_guess:
                guessed_code = player_guess.guess
                if scoring_mode == ScoringMode.EXACT:
                    score_awarded = scoring.calculate_exact_score(
                        correct_code=correct_code, guessed_code=guessed_code
                    )
                elif scoring_mode == ScoringMode.DISTANCE:
                    score_awarded = scoring.calculate_distance_score(
                        correct_code=correct_code, guessed_code=guessed_code
                    )
                else:
                    logger.error(f"Unknown scoring mode: {scoring_mode}")

                # Update player score in Redis
                if score_awarded != 0:
                    updated_player = await room_service.update_player_score(
                        redis=redis,
                        room_code=room_code,
                        nickname=p_nick,
                        score_change=score_awarded,
                    )
                    if updated_player:
                        current_total_score = updated_player.score
                        updated_scores_delta[p_nick] = (
                            current_total_score  # Store new total score for delta
                        )
                    else:
                        logger.warning(f"Failed to update score for player {p_nick} after scoring.")
                        current_total_score = player_data.score  # Use old score if update failed
                else:
                    current_total_score = player_data.score  # Score didn't change
            else:
                # Player didn't guess or wasn't connected? Keep existing score.
                current_total_score = player_data.score

            results.append(
                RoundResultDetail(
                    nickname=p_nick,
                    guess=guessed_code,
                    correct_code=correct_code,
                    score_awarded=score_awarded,
                    current_total_score=current_total_score,
                )
            )

        # --- Update Round State & Broadcast --- #
        round_data.state = RoundStateEnum.SHOWING_RESULTS
        round_data.results = results
        await room_service.set_round_data(redis, room_code, round_data)

        # Broadcast roundResult message
        result_payload = RoundResultPayload(results=results)
        result_message = WSMessage(type="roundResult", payload=result_payload.model_dump())
        await conn_manager.broadcast(result_message.model_dump(), room_code)
        logger.info(
            f"Broadcasted roundResult for round {round_data.round_number} in room {room_code}."
        )

        # Broadcast score updates via delta message if any scores changed
        if updated_scores_delta:
            delta_scores = {"scores": updated_scores_delta}
            delta_message = WSMessage(type="delta", payload=delta_scores)
            await conn_manager.broadcast(delta_message.model_dump(), room_code)
            logger.debug(f"Broadcasted score delta for room {room_code}: {updated_scores_delta}")

        # TODO: Add logic/timer to transition from SHOWING_RESULTS back to WAITING_FOR_SELECTION
        # For now, host must manually start next round?
        # Maybe start a short task here?
        async def _reset_for_next_round(delay: int = 5) -> None:
            await asyncio.sleep(delay)
            rd = await room_service.get_round_data(redis, room_code)
            if rd and rd.state == RoundStateEnum.SHOWING_RESULTS:
                logger.info(f"Resetting state to WAITING_FOR_SELECTION for room {room_code}")
                rd.state = RoundStateEnum.WAITING_FOR_SELECTION
                rd.selected_plane_hex = None
                rd.correct_airport_code = None
                rd.guess_direction = None
                rd.round_start_time = None
                rd.guesses = {}
                rd.results = None
                await room_service.set_round_data(redis, room_code, rd)
                # Maybe broadcast a state update?

        reset_task = asyncio.create_task(_reset_for_next_round())
        conn_manager.add_task(reset_task)  # Add task for tracking
        # Callback to remove task from set when done/cancelled
        reset_task.add_done_callback(conn_manager._remove_task_from_set)

    async def _send_error(
        code: ErrorCode | str, message: str, target_ws: WebSocket | None = None
    ) -> None:
        """Sends a standardized error message to the client."""
        # Ensure 'code' is an ErrorCode enum member before passing to ErrorPayload
        actual_code: ErrorCode
        if isinstance(code, ErrorCode):
            actual_code = code
        else:
            try:
                actual_code = ErrorCode(code)  # Convert string to ErrorCode enum
            except ValueError:
                logger.error(
                    f"Invalid ErrorCode string received: {code}. Defaulting to UNKNOWN_ERROR."
                )
                actual_code = ErrorCode.UNKNOWN_ERROR  # Fallback

        error_payload = ErrorPayload(code=actual_code, message=message)
        error_msg = WSMessage(type=WSMessageType.ERROR, payload=error_payload.model_dump())
        target = target_ws or websocket  # Default to the current connection
        try:
            await conn_manager.send_personal_message(error_msg.model_dump(), target)
        except WebSocketDisconnect:
            logger.warning(f"Failed to send error to {nickname} (already disconnected?).")
        except Exception as e:
            logger.error(f"Failed to send error message: {e}", exc_info=True)

    # --- Heartbeat Task --- #
    async def send_pings(ws: WebSocket, r_code: str, nick: str, mgr: ConnectionManager) -> None:
        """Periodically sends pings and checks for pong responses."""
        ping_seq = 0
        while True:
            await asyncio.sleep(PING_INTERVAL_SECONDS)
            connection_state = mgr.get_connection_state(r_code, nick)

            if (
                not connection_state
                or connection_state.websocket.client_state != WebSocketState.CONNECTED
            ):
                logger.info(
                    f"[Heartbeat:{nick}] Stopping ping task, connection closed or state missing."
                )
                break

            # Check if last pong was too long ago (more robust than just counting)
            # This handles cases where pongs arrive but are delayed.
            time_since_last_pong = time.time() - connection_state.last_pong_received_ts  # noqa: F841

            # Increment missed count *before* sending the next ping
            # If the check below passes, the count reflects pings sent *without* a timely response.
            missed_count = mgr.increment_missed_ping(r_code, nick)

            if missed_count is not None and missed_count > MAX_MISSED_PINGS:
                logger.warning(
                    f"[Heartbeat:{nick}] No pong received for {missed_count} cycles "
                    f"(> {MAX_MISSED_PINGS * PING_INTERVAL_SECONDS}s). Disconnecting."
                )
                await _send_error(
                    ErrorCode.INTERNAL_SERVER_ERROR,  # Or a specific heartbeat timeout error code
                    "Connection timed out due to inactivity.",
                    # Send to the specific socket before closing
                    target_ws=connection_state.websocket,
                )
                # Ensure disconnect is handled gracefully within the manager
                try:
                    # Close the websocket directly before manager cleanup
                    await connection_state.websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                except Exception as close_err:
                    logger.warning(
                        f"[Heartbeat:{nick}] Error closing websocket during timeout: {close_err}"
                    )
                finally:
                    mgr.disconnect(r_code, nick)  # Clean up manager state
                    # Update Redis state (might already be handled by disconnect handler if called)
                    await room_service.update_player_status(redis, r_code, nick, connected=False)
                break  # Exit ping loop

            # Send next ping
            ping_seq += 1
            ping_payload = PingPongPayload(seq=ping_seq)
            ping_msg = WSMessage(type=WSMessageType.PING, payload=ping_payload)
            try:
                logger.debug(f"[Heartbeat:{nick}] Sending PING #{ping_seq}")
                await mgr.send_personal_message(ping_msg.model_dump(), connection_state.websocket)
                # Optionally store outstanding_ping_seq in ConnectionState here
            except WebSocketDisconnect:
                logger.warning(
                    f"[Heartbeat:{nick}] Failed to send ping, client disconnected. Exiting task."
                )
                # Disconnect logic might be handled elsewhere, but ensure loop breaks
                # mgr.disconnect(r_code, nick) # Already handled by main loop's finally?
                break
            except Exception as e:
                logger.error(f"[Heartbeat:{nick}] Error sending ping: {e}", exc_info=True)
                # Decide if we should break or continue trying
                break  # Safer to break on unexpected errors

    # Start the heartbeat task for this connection
    ping_task = asyncio.create_task(send_pings(websocket, room_code, nickname, conn_manager))

    # --- Main Receive Loop --- #
    try:
        logger.debug(f"Starting receive loop for {nickname} in {room_code}.")
        while True:
            try:
                data = await websocket.receive_text()  # Use receive_text for JSON
                logger.debug(f"Received raw data from {nickname}: {data[:100]}...")  # Log snippet

                try:
                    message_data = json.loads(data)
                    # Validate base message structure first
                    ws_msg = WSMessage.model_validate(message_data)
                    logger.debug(f"Parsed WSMessage from {nickname}: type={ws_msg.type}")

                    # Handle specific message types
                    # -----------------------------
                    # Handle PING first as it's frequent
                    if ws_msg.type == WSMessageType.PING:
                        try:
                            ping_payload = PingPongPayload.model_validate(ws_msg.payload)
                            logger.debug(f"Received PING from {nickname} seq={ping_payload.seq}")
                            # Record pong received in ConnectionManager
                            conn_manager.record_pong(room_code, nickname)
                            # Send PONG back
                            pong_payload = PingPongPayload(seq=ping_payload.seq)
                            pong_msg = WSMessage(type=WSMessageType.PONG, payload=pong_payload)
                            await conn_manager.send_personal_message(
                                pong_msg.model_dump(), websocket
                            )
                            logger.debug(f"Sent PONG to {nickname} seq={ping_payload.seq}")
                        except ValidationError as e:
                            logger.warning(f"Invalid PING payload from {nickname}: {e}")
                            await _send_error(
                                ErrorCode.INVALID_PAYLOAD, f"Invalid PING payload: {e}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing PING from {nickname}: {e}", exc_info=True
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Error processing ping."
                            )

                    elif ws_msg.type == WSMessageType.GUESS:
                        # Permission: Any connected player can guess
                        try:
                            guess_payload = GuessPayload.model_validate(ws_msg.payload)
                        except ValidationError as e:
                            logger.warning(f"Invalid GUESS payload: {e}")
                            await _send_error(
                                ErrorCode.INVALID_PAYLOAD, f"Invalid guess payload: {e}"
                            )
                            continue

                        # Fetch fresh round data to ensure state is current
                        current_round_data_local = await room_service.get_round_data(
                            redis, room_code
                        )

                        if not current_round_data_local:
                            logger.error(
                                f"GUESS: Critical - RoundData not found for room {room_code} "
                                "when attempting to guess."
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Round data not found."
                            )
                            continue

                        logger.debug(
                            f"GUESS: Fetched round_data state: {current_round_data_local.state}, "
                            f"for player {nickname}"
                        )

                        if current_round_data_local.state != RoundStateEnum.ACCEPTING_GUESSES:
                            logger.warning(
                                f"Player {nickname} guessed outside active round. State: "
                                f"{current_round_data_local.state}"
                            )
                            await _send_error(
                                ErrorCode.GUESS_OUTSIDE_ROUND,
                                "Guesses only allowed during an active round.",
                            )
                            continue

                        if nickname in current_round_data_local.guesses:
                            logger.warning(f"Player {nickname} already guessed this round.")
                            await _send_error(
                                ErrorCode.ALREADY_GUESSED, "You have already guessed this round."
                            )
                            continue

                        # Store guess
                        player_guess_obj = PlayerGuess(
                            nickname=nickname,
                            guess=guess_payload.airport_code,
                            timestamp=time.time(),
                        )
                        # Merge with any guesses that might have been saved concurrently
                        # Fetch the most recent round data to avoid overwriting other guesses.
                        latest_round_data = await room_service.get_round_data(redis, room_code)
                        if latest_round_data and latest_round_data.guesses:
                            # Start with latest to preserve previously stored guesses.
                            merged_guesses = dict(latest_round_data.guesses)
                        else:
                            merged_guesses = {}
                        # Add / overwrite current player's guess
                        merged_guesses[nickname] = player_guess_obj
                        current_round_data_local.guesses = merged_guesses

                        logger.debug(
                            f"GUESS HANDLER: current_round_data_local before set: "
                            f"{current_round_data_local.model_dump_json(indent=2)}"
                        )

                        # Persist the updated guesses
                        await room_service.set_round_data(
                            redis, room_code, current_round_data_local
                        )
                        logger.info(
                            f"Player {nickname} in room {room_code} guessed "
                            f"{guess_payload.airport_code}."
                        )

                        # Check if all connected players have guessed to end round early
                        all_players_in_room = await room_service.get_all_players(redis, room_code)
                        connected_player_nicks = {
                            p_nick
                            for p_nick, p_data in all_players_in_room.items()
                            if p_data.connected
                        }
                        logger.debug(f"GUESS: All connected players: {connected_player_nicks}")
                        logger.debug(
                            f"GUESS: Current guesses keys: "
                            f"{list(current_round_data_local.guesses.keys())
                               if current_round_data_local.guesses else []}"
                        )

                        # Ensure guesses dict is not None before checking keys
                        if (
                            current_round_data_local.guesses is not None
                            and connected_player_nicks.issubset(
                                current_round_data_local.guesses.keys()
                            )
                        ):
                            logger.info(
                                f"All {len(connected_player_nicks)} connected players have guessed "
                                f"in room {room_code}. Ending round early via "
                                "_end_round(initiator='all_guessed')."
                            )
                            asyncio.create_task(_end_round(initiator="all_guessed"))
                        else:
                            logger.debug(
                                f"GUESS: Not all connected players have guessed yet. "
                                f"Connected: {len(connected_player_nicks)}, "
                                f"Guessed: {len(current_round_data_local.guesses)
                                            if current_round_data_local.guesses else 0}"
                            )

                    elif ws_msg.type == WSMessageType.SELECT_PLANE:
                        if not is_host:
                            await _send_error(
                                ErrorCode.NOT_HOST, "Only the host can select a plane."
                            )
                            continue

                        # Use initialize_round_data to ensure round_data object exists
                        current_round_data_local = await room_service.initialize_round_data(
                            redis, room_code
                        )

                        # Now current_round_data_local is guaranteed to be a RoundData instance
                        if current_round_data_local.state != RoundStateEnum.WAITING_FOR_SELECTION:
                            await _send_error(
                                ErrorCode.INVALID_STATE_FOR_ACTION,
                                "Plane can only be selected when round is waiting for selection.",
                            )
                            continue
                        try:
                            select_payload = SelectPlanePayload.model_validate(ws_msg.payload)
                        except ValidationError as e:
                            logger.warning(f"Invalid SELECT_PLANE payload: {e}")
                            await _send_error(
                                ErrorCode.INVALID_PAYLOAD, f"Invalid select plane payload: {e}"
                            )
                            continue

                        plane_hex_selected = select_payload.hex
                        logger.info(
                            f"Host {nickname} selected plane {plane_hex_selected} for room "
                            f"{room_code}."
                        )

                        # and enrichment services.

                        # MOCKING plane data fetching - this needs real implementation
                        plane_data_from_redis: Optional[PlaneState] = await redis.get_model(
                            f"plane:{plane_hex_selected}", PlaneState
                        )

                        if not plane_data_from_redis:
                            logger.warning(
                                f"Plane {plane_hex_selected} not found in Redis for selection."
                            )
                            await _send_error(
                                ErrorCode.PLANE_NOT_FOUND,
                                f"Plane {plane_hex_selected} data not found.",
                            )
                            continue

                        logger.debug(
                            f"SELECT_PLANE: plane_data_from_redis: "
                            f"{plane_data_from_redis.model_dump_json(indent=2)}"
                        )  # DEBUG LOG

                        # Determine origin, destination, and guess_direction
                        origin_airport = plane_data_from_redis.origin
                        destination_airport = plane_data_from_redis.destination
                        monitored_airport_icao = os.getenv("MONITORED_AIRPORT_ICAO", "KBOS")

                        logger.debug(
                            f"SELECT_PLANE Check Values: origin_airport='{origin_airport}' "
                            f"(type: {type(origin_airport)}), dest_airport='{destination_airport}'"
                            f" (type: {type(destination_airport)}), "
                            f"monitored='{monitored_airport_icao}'"
                        )

                        correct_airport_for_round = None  # Initialize
                        guess_direction = "destination"  # Default

                        # Condition 1: Origin is monitored, and has a destination
                        if origin_airport == monitored_airport_icao and destination_airport:
                            logger.debug(
                                f"SELECT_PLANE Logic: Condition 1 Met. Origin='{origin_airport}', "
                                f"Dest='{destination_airport}'. Guessing Destination."
                            )
                            guess_direction = "destination"
                            correct_airport_for_round = destination_airport
                        # Condition 2: Destination is monitored, and has an origin
                        elif destination_airport == monitored_airport_icao and origin_airport:
                            logger.debug(
                                f"SELECT_PLANE Logic: Condition 2 Met. Origin='{origin_airport}', "
                                f"Dest='{destination_airport}'. Guessing Origin."
                            )
                            guess_direction = "origin"
                            correct_airport_for_round = origin_airport
                        # Condition 3: Has a destination (and not covered by Cond 1 or 2)
                        elif destination_airport:
                            logger.debug(
                                f"SELECT_PLANE Logic: Condition 3 Met. "
                                f"Dest='{destination_airport}'. Guessing Destination."
                            )
                            guess_direction = "destination"
                            correct_airport_for_round = destination_airport
                        # Condition 4: Has an origin (and not covered by Cond 1, 2, or 3)
                        elif origin_airport:
                            logger.debug(
                                f"SELECT_PLANE Logic: Condition 4 Met. "
                                f"Origin='{origin_airport}'. Guessing Origin."
                            )
                            guess_direction = "origin"
                            correct_airport_for_round = origin_airport
                        # Fallback: No origin or destination information available or
                        # they are empty strings
                        else:
                            logger.warning(
                                f"SELECT_PLANE Logic: Fallback - Could not determine guess "
                                f"direction for plane {plane_hex_selected}. Origin: "
                                f"'{origin_airport}', Dest: '{destination_airport}'. "
                                "Defaulting."
                            )
                            guess_direction = "destination"
                            correct_airport_for_round = "UNKNOWN"

                        if not correct_airport_for_round or correct_airport_for_round == "UNKNOWN":
                            logger.error(
                                f"Could not determine correct airport for plane "
                                f"{plane_hex_selected} in SELECT_PLANE."
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR,
                                "Could not determine correct airport for selected plane.",
                            )
                            continue

                        current_round_data_local.selected_plane_hex = plane_hex_selected
                        current_round_data_local.correct_airport_code = (
                            correct_airport_for_round  # Store the actual answer
                        )
                        current_round_data_local.guess_direction = guess_direction
                        # State remains WAITING_FOR_SELECTION until host sends START_ROUND

                        await room_service.set_round_data(
                            redis, room_code, current_round_data_local
                        )

                        # Send planeSelectedConfirm to the host
                        confirm_payload = {  # PlaneSelectedConfirmPayload
                            "hex": plane_hex_selected,
                            "origin": origin_airport if origin_airport else "UNK",
                            "destination": destination_airport if destination_airport else "UNK",
                            "guess_direction": guess_direction,
                        }
                        confirm_msg = WSMessage(
                            type=WSMessageType.PLANE_SELECTED_CONFIRM, payload=confirm_payload
                        )
                        await conn_manager.send_personal_message(
                            confirm_msg.model_dump(mode="json"), websocket
                        )
                        logger.debug(
                            f"Sent PLANE_SELECTED_CONFIRM to host {nickname} for plane "
                            f"{plane_hex_selected}."
                        )

                    elif ws_msg.type == WSMessageType.START_ROUND:
                        if not is_host:
                            await _send_error(
                                ErrorCode.NOT_HOST, "Only the host can start the round."
                            )
                            continue

                        current_round_data_local = await room_service.get_round_data(
                            redis, room_code
                        )
                        room_meta_local = await room_service.get_room_meta(redis, room_code)
                        logger.debug(
                            f"START_ROUND: Fetched round_data: {current_round_data_local}"
                        )  # DEBUG LOG
                        if current_round_data_local:  # Add this check
                            logger.debug(
                                f"START_ROUND: Type of current_round_data_local.state: "
                                f"{type(current_round_data_local.state)}"
                            )
                            logger.debug(
                                f"START_ROUND: Is it RoundStateEnum? "
                                f"{isinstance(current_round_data_local.state, RoundStateEnum)}"
                            )
                        logger.debug(
                            f"START_ROUND: Fetched room_meta: {room_meta_local}"
                        )  # DEBUG LOG

                        if not current_round_data_local or not room_meta_local:
                            logger.error(
                                f"START_ROUND: Missing round or meta data for room {room_code}"
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Room or round data not found."
                            )
                            continue

                        logger.debug(
                            f"START_ROUND: Plane selected: "
                            f"{current_round_data_local.selected_plane_hex}, "
                            f"Correct airport: "
                            f"{current_round_data_local.correct_airport_code}"
                        )  # DEBUG LOG
                        if (
                            not current_round_data_local.selected_plane_hex
                            or not current_round_data_local.correct_airport_code
                        ):
                            await _send_error(
                                ErrorCode.INVALID_STATE_FOR_ACTION,
                                "A plane must be selected with a valid correct airport "
                                "before starting the round.",
                            )  # Modified error message
                            continue

                        logger.debug(
                            f"START_ROUND: Current round state: "
                            f"{current_round_data_local.state.value}"
                        )  # DEBUG LOG
                        # Implicitly, after plane selection, state is still WAITING_FOR_SELECTION.
                        # Or, if we introduce an intermediate state like PLANE_SELECTED,
                        # check for that.
                        if current_round_data_local.state != RoundStateEnum.WAITING_FOR_SELECTION:
                            await _send_error(
                                ErrorCode.INVALID_STATE_FOR_ACTION,
                                f"Round cannot be started from state: "
                                f"{current_round_data_local.state.value}",
                            )
                            continue

                        # Increment round number if this is not the very first round start attempt
                        # for this selection
                        # If round_start_time is None, it's the first start for this selected plane
                        if current_round_data_local.round_start_time is None:
                            current_round_data_local.round_number += 1

                        current_round_data_local.state = RoundStateEnum.ACCEPTING_GUESSES
                        current_round_data_local.round_start_time = time.time()
                        current_round_data_local.guesses = {}  # Clear previous guesses
                        # for this round selection
                        current_round_data_local.results = None  # Clear previous results

                        await room_service.set_round_data(
                            redis, room_code, current_round_data_local
                        )

                        round_start_payload = RoundStartPayload(
                            hex=current_round_data_local.selected_plane_hex,
                            timeout_s=room_meta_local.round_timeout_seconds,
                            direction=current_round_data_local.guess_direction
                            or "destination",  # Default if somehow not set
                            round_number=current_round_data_local.round_number,
                        )
                        round_start_message = WSMessage(
                            type=WSMessageType.ROUND_START, payload=round_start_payload
                        )
                        await conn_manager.broadcast(
                            round_start_message.model_dump(mode="json"), room_code
                        )
                        logger.info(
                            f"Round {current_round_data_local.round_number} started in room "
                            f"{room_code} by {nickname}. Plane: "
                            f"{current_round_data_local.selected_plane_hex}"
                        )

                        # Cancel any existing round timer before starting a new one
                        if round_timer_task and not round_timer_task.done():
                            logger.debug(f"Cancelling existing round timer for room {room_code}")
                            round_timer_task.cancel()

                        async def _round_timeout_wrapper(timeout_seconds: int) -> None:
                            await asyncio.sleep(timeout_seconds)
                            logger.info(
                                f"Round timer expired for room {room_code}. "
                                "Attempting to end round."
                            )
                            await _end_round(initiator="timer")

                        round_timer_task = asyncio.create_task(
                            _round_timeout_wrapper(room_meta_local.round_timeout_seconds),
                            name=f"round_timer_{room_code}_{current_round_data_local.round_number}",
                        )
                        conn_manager.add_task(round_timer_task)
                        round_timer_task.add_done_callback(conn_manager._remove_task_from_set)

                    elif ws_msg.type == WSMessageType.SKIP_ROUND:
                        # ... (existing skip round logic)
                        pass  # Placeholder for brevity

                    elif ws_msg.type == WSMessageType.TRANSFER_HOST:
                        # ... (existing transfer host logic)
                        pass  # Placeholder for brevity

                    elif ws_msg.type == WSMessageType.CLAIM_HOST:
                        # Non-host player requests to become host after original host disconnect.
                        if is_host:
                            await _send_error(
                                ErrorCode.CANNOT_TRANSFER_TO_SELF, "You are already the host."
                            )
                            continue

                        # Retrieve latest room metadata.
                        room_meta_local = await room_service.get_room_meta(redis, room_code)
                        if not room_meta_local:
                            await _send_error(ErrorCode.ROOM_NOT_FOUND, "Room not found.")
                            continue

                        # If the host is still marked as connected, reject.
                        if room_meta_local.host_disconnected_ts is None:
                            await _send_error(
                                ErrorCode.CLAIM_HOST_STILL_CONNECTED,
                                "Current host is still connected.",
                            )
                            continue

                        # Check if claim window has opened.
                        elapsed = time.time() - room_meta_local.host_disconnected_ts
                        if elapsed < HOST_DISCONNECT_CLAIM_WINDOW_SECONDS:
                            await _send_error(
                                ErrorCode.CLAIM_HOST_TOO_EARLY, "Claim window has not opened yet."
                            )
                            continue

                        # All good – promote claimer.
                        previous_host = room_meta_local.host_nickname
                        room_meta_local.host_nickname = nickname
                        room_meta_local.host_disconnected_ts = None
                        await room_service.set_room_meta(redis, room_code, room_meta_local)

                        # Broadcast newHost message.
                        new_host_payload = NewHostPayload(nickname=nickname)
                        new_host_message = WSMessage(
                            type=WSMessageType.NEW_HOST, payload=new_host_payload.model_dump()
                        )
                        await conn_manager.broadcast(new_host_message.model_dump(), room_code)
                        logger.info(
                            f"Player {nickname} claimed host from {previous_host} in room "
                            f"{room_code}."
                        )

                        # Cancel any pending auto-transfer tasks.
                        if auto_transfer_host_task and not auto_transfer_host_task.done():
                            auto_transfer_host_task.cancel()

                        # Update local flag so this connection is recognised
                        # as host for future actions.
                        is_host = True

                    elif ws_msg.type == WSMessageType.LEAVE:
                        logger.info(f"Received LEAVE message from {nickname}. Disconnecting.")
                        break  # Exit receive loop, finally block will handle cleanup

                    else:
                        logger.warning(
                            f"Received unhandled message type from {nickname}: {ws_msg.type}"
                        )
                        await _send_error(
                            ErrorCode.INVALID_MESSAGE_FORMAT,  # Or a more specific code
                            f"Message type '{ws_msg.type}' is not recognized or handled.",
                        )

                except json.JSONDecodeError:
                    logger.warning(f"Received invalid JSON from {nickname}: {data[:100]}...")
                    await _send_error(ErrorCode.INVALID_MESSAGE_FORMAT, "Invalid JSON received.")
                except ValidationError as e:
                    # Error validating WSMessage structure itself or specific payload
                    logger.warning(
                        f"WS Message validation failed for {nickname}: {e} - Data: {data[:100]}..."
                    )
                    await _send_error(ErrorCode.INVALID_PAYLOAD, f"Invalid message structure: {e}")
                except Exception as e:
                    # Catch-all for unexpected errors during message processing
                    logger.error(
                        f"Unexpected error processing message from {nickname}: {e}", exc_info=True
                    )
                    await _send_error(
                        ErrorCode.INTERNAL_SERVER_ERROR, "An internal error occurred."
                    )

            except WebSocketDisconnect as e:
                logger.info(
                    f"WebSocket disconnected for {nickname} in {room_code} "
                    f"(code: {e.code}, reason: {e.reason})."
                )
                break  # Exit receive loop
            except Exception as e:
                # Catch unexpected errors in receive_text itself
                logger.error(
                    f"Unexpected error in receive loop for {nickname} in {room_code}: {e}",
                    exc_info=True,
                )
                # Consider breaking the loop on unexpected errors to prevent infinite loops
                break

    finally:
        # --- Cleanup on Disconnect --- #
        logger.info(f"Cleaning up connection for {nickname} in {room_code}.")

        # Cancel the ping task
        if ping_task and not ping_task.done():
            ping_task.cancel()
            try:
                await ping_task  # Allow task to handle cancellation
            except asyncio.CancelledError:
                logger.debug(f"Ping task for {nickname} cancelled successfully.")
            except Exception as e:
                logger.error(
                    f"Error during ping task cancellation for {nickname}: {e}", exc_info=True
                )

        # Cancel other tasks if necessary
        # ... cancel round_timer_task, host_disconnect_check_task, etc. ...
        # Example:
        # if round_timer_task and not round_timer_task.done():
        #     round_timer_task.cancel()
        #     # await task if needed

        # Remove from connection manager
        conn_manager.disconnect(room_code, nickname)

        # Update player status in Redis
        try:
            await room_service.update_player_status(redis, room_code, nickname, connected=False)
        except Exception as e:
            logger.error(
                f"Failed to update player status to disconnected for {nickname} in "
                f"{room_code}: {e}",
                exc_info=True,
            )

        # Broadcast Player Left message
        # Important: Do this *after* updating Redis status
        # Check if room still exists in manager (might have been deleted if last player)
        if room_code in conn_manager.active_connections:
            left_payload_model = PlayerLeftPayload(nickname=nickname)
            # Ensure the inner payload is dumped to a dict
            left_msg = WSMessage(
                type=WSMessageType.PLAYER_LEFT, payload=left_payload_model.model_dump()
            )
            broadcast_data_left = left_msg.model_dump()
            logger.debug(f"Broadcasting PLAYER_LEFT with data: {broadcast_data_left}")
            # No need to exclude self, already disconnected
            await conn_manager.broadcast(broadcast_data_left, room_code)
        else:
            logger.info(
                f"Room {room_code} empty or deleted, skipping playerLeft broadcast for {nickname}."
            )

        # Handle host leaving logic
        # Fetch meta again in case it changed
        final_room_meta = await room_service.get_room_meta(redis, room_code)
        if final_room_meta and final_room_meta.host_nickname == nickname:
            logger.info(
                f"Host {nickname} disconnected from room {room_code}. Initiating handover checks."
            )
            await _handle_host_disconnect()  # Start timers/allow claim
        else:
            # If a non-host disconnected, clear any pending host disconnect timers
            # This might happen if host disconnects, then rejoins quickly before claim
            # But needs careful consideration if multiple non-hosts can trigger this.
            # await _clear_host_disconnect_state() # Maybe too aggressive?
            pass


# --- Background Task: Ping ---


@router.get(
    "/{code}",
    response_model=RoomState,
    summary="Get Full Room Details (Debug)",
    tags=["rooms", "debug"],
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Room not found"},
    },
)
async def get_room_details(
    code: str = Path(
        ...,
        description="The 4-letter room code.",
        min_length=4,
        max_length=4,
        pattern="^[A-Z]{4}$",
    ),
    redis: RedisClient = Depends(get_redis),
) -> RoomState:
    """
    Retrieves the complete state of a specific game room from Redis.

    Intended primarily for debugging and development purposes.

    - **code**: The unique 4-letter code identifying the room.
    - **Returns**: The full state of the room including metadata, players, scores, and round status.
    - **Raises**: `HTTPException` (404) if the room code is not found in Redis.
    """
    try:
        room_meta = await room_service.get_room_meta(redis, code)
        if not room_meta:
            # Let FastAPI handle this HTTPException directly
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Room with code '{code}' not found.",
            )

        # Fetch other data only if room_meta was found
        players = await room_service.get_all_players(redis, code)
        round_data = await room_service.get_round_data(redis, code)

    except HTTPException:  # Explicitly re-raise HTTPExceptions
        raise
    except Exception as e:  # Catch other unexpected errors
        logger.error(f"Unexpected error fetching room details for {code}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred.",
        ) from e

    # Assemble the response model (only if successful)
    room_state = RoomState(
        code=code,
        mode=room_meta.mode,
        round_timeout_seconds=room_meta.round_timeout_seconds,
        host_nickname=room_meta.host_nickname,
        created_ts=room_meta.created_ts,
        players=players,  # get_all_players returns Dict[str, Player]
        current_round=round_data,  # get_round_data returns Optional[RoundData]
    )

    return room_state


@router.delete(
    "/{code}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End (delete) a game room",
    tags=["rooms"],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Room not found"}},
)
async def delete_room_endpoint(
    code: str = Path(
        ..., description="The 4-letter room code.", min_length=4, max_length=4, pattern="^[A-Z]{4}$"
    ),
    redis: RedisClient = Depends(get_redis),
) -> None:
    """Delete all Redis keys for a room.

    Primarily for host/admin cleanup; no authentication enforced yet.
    """
    room_meta = await room_service.get_room_meta(redis, code)
    if not room_meta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found.")
    try:
        await room_service.delete_room(redis, code)
    except Exception as exc:  # Unexpected errors
        logger.error("Failed to delete room %s: %s", code, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to delete room."
        ) from exc

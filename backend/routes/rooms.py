import asyncio
import json
import logging
import random
import time
from typing import List, Optional
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from backend.schemas.core import Player, RoomMeta
from backend.schemas.game import (
    PlayerGuess,
    RoundResultDetail,
    RoundStateEnum,
    SoloSelectionContext,
)
from backend.schemas.plane import PlaneState
from backend.schemas.room import (
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinRequest,
    RoomJoinResponse,
    generate_room_code,
)
from backend.schemas.ws import (
    ErrorCode,
    ErrorPayload,
    FullRoomState,
    GuessPayload,
    NewHostPayload,
    PingPongPayload,
    PlaneSelectedConfirmPayload,
    PlayerJoinedPayload,
    PlayerLeftPayload,
    RoundResultPayload,
    RoundStartPayload,
    SelectPlanePayload,
    TransferHostPayload,
    WSMessage,
    WSMessageType,
)
from backend.services import room_service, scoring
from backend.services.presence import record_gameplay_activity
from backend.services.round_target import (
    RoundTarget,
    RouteProblem,
    monitored_airport_icao,
    resolve_round_target,
)
from backend.settings import get_settings
from backend.utils.airport_db import resolve_airport
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

# How long a host who left the room empty can be away before another player may claim host.
HOST_DISCONNECT_CLAIM_WINDOW_SECONDS = get_settings().host_disconnect_claim_window_seconds


def _ws_base_url(request: Request) -> str:
    """Base of the ws_url in join responses: WS_BASE_URL if set, else the request's own origin."""
    return get_settings().ws_base_url or str(request.base_url).replace("http", "ws", 1)


# Heartbeat constants
PING_INTERVAL_SECONDS = 10  # Send a ping every 10 seconds
MAX_MISSED_PINGS = 3  # Disconnect after 3 missed pongs (e.g., 30 seconds total timeout)

logger = logging.getLogger(__name__)

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


# WS message types that count as someone actively playing, which keeps paid
# flight enrichment running. Heartbeats, reconnects and host management do not.
GAMEPLAY_ACTIVITY_TYPES = frozenset(
    {
        WSMessageType.SELECT_PLANE,
        WSMessageType.START_ROUND,
        WSMessageType.GUESS,
        WSMessageType.SKIP_ROUND,
    }
)


async def _record_ws_activity(redis: RedisClient, message_type: str) -> None:
    if message_type in GAMEPLAY_ACTIVITY_TYPES:
        await record_gameplay_activity(redis)


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


def _selection_rejection(
    target: RoundTarget, monitored_airport: str, *, solo: bool
) -> tuple[ErrorCode, str]:
    """Return the error sent when the host selects a plane that can't be played."""
    if target.problem is RouteProblem.NOT_MONITORED:
        return (
            ErrorCode.INVALID_PLANE_SELECTION,
            f"Flight must be departing from or arriving at {monitored_airport}.",
        )
    if target.problem is RouteProblem.UNKNOWN_ANSWER_AIRPORT:
        # The answer airport is never named: no message before roundResult carries it.
        return (
            ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS,
            f"This flight's {target.guess_direction} airport "
            "isn't in the game's airport list. Pick another flight.",
        )
    # MISSING_ANSWER keeps the codes each mode has always sent.
    if solo:
        return (
            ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS,
            "Selected plane has insufficient route data",
        )
    return (
        ErrorCode.INTERNAL_SERVER_ERROR,
        "Could not determine correct airport for selected plane.",
    )


def _round_busy_message(state: RoundStateEnum) -> str:
    """Return the error shown to a host who selects a plane or starts a round too early.

    Args:
        state: The round's state, which is not ``WAITING_FOR_SELECTION``.

    Returns:
        A message the frontend shows to the player as is.
    """
    if state == RoundStateEnum.SHOWING_RESULTS:
        # _reset_for_next_round reopens selection a few seconds after roundResult.
        return "The last round just ended. You can start the next one in a few seconds."
    return "A round is already in progress."


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

    base_ws_url = _ws_base_url(request)

    # URL-encode room code and nickname to handle special characters
    encoded_room = quote(room_code, safe="")
    encoded_nickname = quote(room_data.host_nickname, safe="")
    ws_url = f"{base_ws_url}api/v0/rooms/ws/{encoded_room}/{encoded_nickname}"

    # Set Location header (as specified in PRD)
    response.headers["Location"] = ws_url

    await record_gameplay_activity(redis)
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
    # Solo mode special case
    if room_code == "solo":
        solo_code, _ = await room_service.create_solo_room_instance(join_data.nickname, redis)
        base_ws_url = _ws_base_url(request)
        # URL-encode room code and nickname to handle special characters (solo: prefix has colon)
        encoded_room = quote(solo_code, safe="")
        encoded_nickname = quote(join_data.nickname, safe="")
        ws_url = f"{base_ws_url}api/v0/rooms/ws/{encoded_room}/{encoded_nickname}"
        await record_gameplay_activity(redis)
        return RoomJoinResponse(room_code=solo_code, ws_url=ws_url)

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

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add player to room in Redis: {e}",
        ) from e

    # 5. Construct WebSocket URL
    base_ws_url = _ws_base_url(request)
    # URL-encode room code and nickname to handle special characters
    encoded_room = quote(room_code, safe="")
    encoded_nickname = quote(join_data.nickname, safe="")
    ws_url = f"{base_ws_url}api/v0/rooms/ws/{encoded_room}/{encoded_nickname}"

    await record_gameplay_activity(redis)
    return RoomJoinResponse(room_code=room_code, ws_url=ws_url)


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

    is_solo_mode = room_code.startswith("solo:")

    # Define _send_error early so it's available to both solo and multiplayer code paths
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

    async def _send_unknown_airport_error(code: str) -> None:
        logger.info(f"Rejecting guess '{code}' from {nickname} in {room_code}: unknown airport")
        await _send_error(
            ErrorCode.UNKNOWN_AIRPORT_CODE,
            f"Unknown airport code '{code}'. Enter an IATA (ORD) or ICAO (KORD) code.",
        )

    async def _reject_unknown_guess_code(code: str) -> bool:
        """Send UNKNOWN_AIRPORT_CODE and return True when ``code`` isn't in the dataset."""
        if resolve_airport(code) is not None:
            return False
        await _send_unknown_airport_error(code)
        return True

    if is_solo_mode:

        async def _solo_loop() -> None:
            while True:
                data = await websocket.receive_json()
                try:
                    ws_msg = WSMessage.model_validate(data)
                except ValidationError:
                    await _send_error(ErrorCode.INVALID_MESSAGE_FORMAT, "Invalid message format")
                    continue
                await _record_ws_activity(redis, ws_msg.type)

                # Handle PING from client - respond with PONG
                if ws_msg.type == WSMessageType.PING:
                    try:
                        ping_payload = PingPongPayload.model_validate(ws_msg.payload)
                        pong_payload = PingPongPayload(seq=ping_payload.seq)
                        pong_msg = WSMessage(type=WSMessageType.PONG, payload=pong_payload)
                        await conn_manager.send_personal_message(pong_msg.model_dump(), websocket)
                        logger.debug(f"[Solo] Sent PONG to {nickname} seq={ping_payload.seq}")
                    except ValidationError as e:
                        logger.warning(f"[Solo] Invalid PING payload from {nickname}: {e}")
                        await _send_error(ErrorCode.INVALID_PAYLOAD, f"Invalid PING payload: {e}")
                    continue

                # Handle PONG from client (in response to server-initiated ping, if any)
                if ws_msg.type == WSMessageType.PONG:
                    # Record the pong for heartbeat tracking
                    conn_manager.record_pong(room_code, nickname)
                    logger.debug(f"[Solo] Received PONG from {nickname}")
                    continue

                if ws_msg.type == WSMessageType.SELECT_PLANE:
                    try:
                        select_payload = SelectPlanePayload.model_validate(ws_msg.payload)
                    except ValidationError as e:
                        await _send_error(
                            ErrorCode.INVALID_PAYLOAD,
                            f"Invalid selectPlane payload: {e}",
                        )
                        continue

                    plane = await redis.get_model(f"plane:{select_payload.hex}", PlaneState)
                    if not plane:
                        await _send_error(ErrorCode.PLANE_NOT_FOUND, "Plane not found")
                        continue

                    monitored_airport = monitored_airport_icao()
                    target = resolve_round_target(
                        plane.origin, plane.destination, monitored_airport
                    )
                    if not target.is_playable:
                        logger.info(
                            f"[Solo] Rejecting plane {select_payload.hex} "
                            f"({plane.origin} -> {plane.destination}): {target.problem}"
                        )
                        await _send_error(
                            *_selection_rejection(target, monitored_airport, solo=True)
                        )
                        continue

                    context = SoloSelectionContext(
                        selected_plane_hex=select_payload.hex,
                        correct_airport_code=target.answer_code,
                        guess_direction=target.guess_direction,
                    )
                    await room_service.set_solo_player_selection_context(redis, room_code, context)

                    confirm_msg = WSMessage(
                        type=WSMessageType.PLANE_SELECTED_CONFIRM,
                        payload=PlaneSelectedConfirmPayload(
                            hex=select_payload.hex, guess_direction=target.guess_direction
                        ).model_dump(),
                    )
                    await conn_manager.send_personal_message(confirm_msg.model_dump(), websocket)

                elif ws_msg.type == WSMessageType.GUESS:
                    try:
                        guess_payload = GuessPayload.model_validate(ws_msg.payload)
                    except ValidationError as e:
                        await _send_error(
                            ErrorCode.INVALID_PAYLOAD,
                            f"Invalid guess payload: {e}",
                        )
                        continue

                    context = await room_service.get_solo_player_selection_context(redis, room_code)
                    if not context or not context.selected_plane_hex:
                        await _send_error(
                            ErrorCode.INVALID_STATE_FOR_ACTION,
                            "Select a plane first",
                        )
                        continue

                    room_meta_local = await room_service.get_room_meta(redis, room_code)
                    if not room_meta_local:
                        await _send_error(ErrorCode.ROOM_NOT_FOUND, "Room not found")
                        continue

                    # The selection stays in place, so the player can guess again.
                    if await _reject_unknown_guess_code(guess_payload.airport_code):
                        continue

                    guess_score = scoring.score_guess(
                        room_meta_local.mode,
                        context.correct_airport_code,
                        guess_payload.airport_code,
                    )

                    updated = await room_service.update_player_score(
                        redis, room_code, nickname, guess_score.points
                    )
                    total_score = updated.score if updated else 0

                    result_detail = RoundResultDetail(
                        nickname=nickname,
                        guess=guess_payload.airport_code,
                        correct_code=context.correct_airport_code or "",
                        score_awarded=guess_score.points,
                        current_total_score=total_score,
                        distance_km=guess_score.distance_km,
                    )
                    result_payload = RoundResultPayload(
                        results=[result_detail], hex=context.selected_plane_hex
                    )
                    result_msg = WSMessage(
                        type=WSMessageType.ROUND_RESULT,
                        payload=result_payload.model_dump(),
                    )
                    await conn_manager.send_personal_message(result_msg.model_dump(), websocket)
                    await room_service.clear_solo_player_selection_context(redis, room_code)

                elif ws_msg.type == WSMessageType.LEAVE:
                    break

                elif ws_msg.type == WSMessageType.START_ROUND:
                    # Handle START_ROUND in solo mode - send roundStart to frontend
                    context = await room_service.get_solo_player_selection_context(redis, room_code)
                    if not context or not context.selected_plane_hex:
                        await _send_error(
                            ErrorCode.INVALID_STATE_FOR_ACTION,
                            "Select a plane first before starting the round",
                        )
                        continue

                    # Send roundStart message so frontend shows guess form
                    round_start_payload = {
                        "hex": context.selected_plane_hex,
                        "direction": context.guess_direction,
                        "timeout_s": 60,  # Solo mode has no timeout pressure
                        "round_number": 1,  # Solo mode doesn't track round numbers
                    }
                    round_start_msg = WSMessage(
                        type=WSMessageType.ROUND_START,
                        payload=round_start_payload,
                    )
                    await conn_manager.send_personal_message(
                        round_start_msg.model_dump(), websocket
                    )
                    plane_hex = context.selected_plane_hex
                    logger.info(f"[Solo] Round started for {nickname} with plane {plane_hex}")

                elif ws_msg.type in {
                    WSMessageType.SKIP_ROUND,
                    WSMessageType.TRANSFER_HOST,
                    WSMessageType.CLAIM_HOST,
                }:
                    await _send_error(
                        ErrorCode.INVALID_ACTION_IN_SOLO_MODE,
                        "This action is not available in solo mode.",
                    )
                else:
                    await _send_error(
                        ErrorCode.INVALID_MESSAGE_FORMAT,
                        f"Unhandled message type {ws_msg.type}",
                    )

        try:
            await _solo_loop()
        except WebSocketDisconnect:
            logger.info(f"[Solo] Player {nickname} disconnected from room {room_code}.")
        except Exception as e:
            logger.error(
                f"[Solo] Unexpected error in solo loop for {nickname} in {room_code}: {e}",
                exc_info=True,
            )
        finally:
            # Cleanup solo room resources
            await room_service.delete_room(redis, room_code)
            await room_service.update_player_status(redis, room_code, nickname, connected=False)
            conn_manager.disconnect(room_code, nickname)
        return
    # --- Broadcast Player Joined --- #
    # Exclude self from broadcast
    join_payload_model = PlayerJoinedPayload(nickname=nickname)
    # Ensure the inner payload is dumped to a dict before being assigned to WSMessage
    join_msg = WSMessage(type=WSMessageType.PLAYER_JOINED, payload=join_payload_model.model_dump())
    broadcast_data_join = join_msg.model_dump()  # Now this should have the payload as a dict
    logger.debug(f"Broadcasting PLAYER_JOINED with data: {broadcast_data_join}")
    await conn_manager.broadcast(broadcast_data_join, room_code, exclude_nickname=nickname)

    # --- Game Logic / Host State Setup --- #
    room_meta_for_logic = await room_service.get_room_meta(redis, room_code)
    is_host = room_meta_for_logic and room_meta_for_logic.host_nickname == nickname

    # Timer tasks (need to be managed)
    auto_transfer_host_task: Optional[asyncio.Task] = None
    round_timer_task: Optional[asyncio.Task] = None

    # --- Helper Functions (defined within endpoint scope for context access) --- #

    async def _handle_host_disconnect() -> None:
        """Records the host disconnect time in Redis."""
        nonlocal auto_transfer_host_task
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

            new_host = random.choice(connected_players)  # noqa: S311 (not security-sensitive)
            current_meta_check.host_nickname = new_host.nickname
            current_meta_check.host_disconnected_ts = None  # Clear disconnect time
            await room_service.set_room_meta(redis, room_code, current_meta_check)
            logger.info(f"Auto-transferring host to {new_host.nickname} in room {room_code}.")

            # Broadcast newHost message
            new_host_payload = NewHostPayload(nickname=new_host.nickname)
            new_host_message = WSMessage(
                type=WSMessageType.NEW_HOST, payload=new_host_payload.model_dump()
            )
            await conn_manager.broadcast(new_host_message.model_dump(), room_code)

        auto_transfer_host_task = asyncio.create_task(
            _auto_transfer_host(), name=f"auto_transfer_{room_code}"
        )
        conn_manager.add_task(auto_transfer_host_task)  # Add task for tracking
        # Callback to remove task from set when done/cancelled
        auto_transfer_host_task.add_done_callback(conn_manager._remove_task_from_set)

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
            distance_km = None  # Only populated for Distance mode

            if player_guess:
                guessed_code = player_guess.guess
                guess_score = scoring.score_guess(scoring_mode, correct_code, guessed_code)
                score_awarded = guess_score.points
                distance_km = guess_score.distance_km

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
                    distance_km=distance_km,  # Add distance_km to results
                )
            )

        # --- Update Round State & Broadcast --- #
        round_data.state = RoundStateEnum.SHOWING_RESULTS
        round_data.results = results
        await room_service.set_round_data(redis, room_code, round_data)

        # Broadcast roundResult message
        result_payload = RoundResultPayload(results=results, hex=round_data.selected_plane_hex)
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

    async def _check_is_host() -> bool:
        """Check if the current player is the host by fetching current room metadata."""
        room_meta_check = await room_service.get_room_meta(redis, room_code)
        return room_meta_check is not None and room_meta_check.host_nickname == nickname

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
                    await _record_ws_activity(redis, ws_msg.type)

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

                    elif ws_msg.type == WSMessageType.PONG:
                        try:
                            pong_payload = PingPongPayload.model_validate(ws_msg.payload)
                            logger.debug(f"Received PONG from {nickname} seq={pong_payload.seq}")
                            # Record pong received in ConnectionManager
                            conn_manager.record_pong(room_code, nickname)
                        except ValidationError as e:
                            logger.warning(f"Invalid PONG payload from {nickname}: {e}")
                            await _send_error(
                                ErrorCode.INVALID_PAYLOAD, f"Invalid PONG payload: {e}"
                            )
                        except Exception as e:
                            logger.error(
                                f"Error processing PONG from {nickname}: {e}", exc_info=True
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Error processing pong."
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

                        player_guess_obj = PlayerGuess(
                            nickname=nickname,
                            guess=guess_payload.airport_code,
                            timestamp=time.time(),
                        )
                        outcome, round_data_for_guess = await room_service.record_guess(
                            redis, room_code, player_guess_obj
                        )

                        if outcome == room_service.GuessOutcome.NO_ROUND:
                            logger.error(
                                f"GUESS: Critical - RoundData not found for room {room_code} "
                                "when attempting to guess."
                            )
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Round data not found."
                            )
                            continue

                        if outcome == room_service.GuessOutcome.NOT_ACCEPTING:
                            logger.warning(
                                f"Player {nickname} guessed outside active round. State: "
                                f"{round_data_for_guess.state}"
                            )
                            await _send_error(
                                ErrorCode.GUESS_OUTSIDE_ROUND,
                                "Guesses only allowed during an active round.",
                            )
                            continue

                        if outcome == room_service.GuessOutcome.ALREADY_GUESSED:
                            logger.warning(f"Player {nickname} already guessed this round.")
                            await _send_error(
                                ErrorCode.ALREADY_GUESSED, "You have already guessed this round."
                            )
                            continue

                        # record_guess checks this after the round-state errors so they keep
                        # precedence; an unknown code is never stored, so the player can retry.
                        if outcome == room_service.GuessOutcome.UNKNOWN_AIRPORT:
                            await _send_unknown_airport_error(guess_payload.airport_code)
                            continue

                        logger.info(
                            f"Player {nickname} in room {room_code} guessed "
                            f"{guess_payload.airport_code}."
                        )

                        # record_guess serialises concurrent guesses, so the handler that
                        # records the last outstanding guess sees every guess here.
                        all_players_in_room = await room_service.get_all_players(redis, room_code)
                        connected_player_nicks = {
                            p_nick
                            for p_nick, p_data in all_players_in_room.items()
                            if p_data.connected
                        }
                        if connected_player_nicks.issubset(round_data_for_guess.guesses.keys()):
                            logger.info(
                                f"All {len(connected_player_nicks)} connected players have guessed "
                                f"in room {room_code}. Ending round early via "
                                "_end_round(initiator='all_guessed')."
                            )
                            # Create a task to avoid blocking the current message handler.
                            # conn_manager keeps a reference: the loop holds tasks only weakly.
                            end_round_task = asyncio.create_task(
                                _end_round(initiator="all_guessed"), name=f"end_round_{room_code}"
                            )
                            conn_manager.add_task(end_round_task)
                            end_round_task.add_done_callback(conn_manager._remove_task_from_set)
                        else:
                            logger.debug(
                                "GUESS: Not all connected players have guessed yet. "
                                "Connected: %d, Guessed: %d",
                                len(connected_player_nicks),
                                len(round_data_for_guess.guesses),
                            )

                    elif ws_msg.type == WSMessageType.SELECT_PLANE:
                        # Check host status dynamically to handle host transfers
                        if not await _check_is_host():
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
                                _round_busy_message(current_round_data_local.state),
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

                        origin_airport = plane_data_from_redis.origin
                        destination_airport = plane_data_from_redis.destination
                        monitored_airport = monitored_airport_icao()
                        target = resolve_round_target(
                            origin_airport, destination_airport, monitored_airport
                        )
                        if not target.is_playable:
                            logger.info(
                                f"Rejecting plane {plane_hex_selected} "
                                f"({origin_airport} -> {destination_airport}): {target.problem}"
                            )
                            await _send_error(
                                *_selection_rejection(target, monitored_airport, solo=False)
                            )
                            continue

                        current_round_data_local.selected_plane_hex = plane_hex_selected
                        current_round_data_local.correct_airport_code = target.answer_code
                        current_round_data_local.guess_direction = target.guess_direction
                        # State remains WAITING_FOR_SELECTION until host sends START_ROUND

                        await room_service.set_round_data(
                            redis, room_code, current_round_data_local
                        )

                        # The host is also a player, so the confirm carries no airports.
                        confirm_msg = WSMessage(
                            type=WSMessageType.PLANE_SELECTED_CONFIRM,
                            payload=PlaneSelectedConfirmPayload(
                                hex=plane_hex_selected, guess_direction=target.guess_direction
                            ).model_dump(),
                        )
                        await conn_manager.send_personal_message(
                            confirm_msg.model_dump(mode="json"), websocket
                        )
                        logger.debug(
                            f"Sent PLANE_SELECTED_CONFIRM to host {nickname} for plane "
                            f"{plane_hex_selected}."
                        )

                    elif ws_msg.type == WSMessageType.START_ROUND:
                        # Check host status dynamically to handle host transfers
                        if not await _check_is_host():
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
                                _round_busy_message(current_round_data_local.state),
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
                            type=WSMessageType.ROUND_START, payload=round_start_payload.model_dump()
                        )

                        # Debug logging for roundStart broadcast
                        logger.info(f"About to broadcast roundStart message to room {room_code}")
                        logger.info(f"RoundStart payload: {round_start_payload.model_dump()}")
                        logger.info(f"Full message: {round_start_message.model_dump(mode='json')}")

                        await conn_manager.broadcast(
                            round_start_message.model_dump(mode="json"), room_code
                        )

                        logger.info(f"roundStart broadcast completed for room {room_code}")
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
                        # Check host status dynamically to handle host transfers
                        if not await _check_is_host():
                            await _send_error(
                                ErrorCode.NOT_HOST, "Only the host can skip the round."
                            )
                            continue

                        current_round = await room_service.get_round_data(redis, room_code)
                        if not current_round:
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR, "Round data not found."
                            )
                            continue

                        # Reset round state
                        current_round.state = RoundStateEnum.WAITING_FOR_SELECTION
                        current_round.selected_plane_hex = None
                        current_round.correct_airport_code = None
                        current_round.guess_direction = None
                        current_round.round_start_time = None
                        current_round.guesses = {}
                        current_round.results = None

                        await room_service.set_round_data(redis, room_code, current_round)

                        if round_timer_task and not round_timer_task.done():
                            round_timer_task.cancel()
                            round_timer_task = None

                        delta_payload = {
                            "round": {
                                "state": current_round.state.value,
                                "round_number": current_round.round_number,
                            }
                        }
                        delta_msg = WSMessage(type=WSMessageType.DELTA, payload=delta_payload)
                        await conn_manager.broadcast(delta_msg.model_dump(mode="json"), room_code)
                        logger.info(f"Host {nickname} skipped round in room {room_code}.")

                    elif ws_msg.type == WSMessageType.TRANSFER_HOST:
                        # Host transfers host privileges to another player
                        # Check host status dynamically to handle host transfers
                        if not await _check_is_host():
                            await _send_error(
                                ErrorCode.NOT_HOST, "Only the host can transfer host privileges."
                            )
                            continue

                        try:
                            transfer_payload = TransferHostPayload.model_validate(ws_msg.payload)
                        except ValidationError as e:
                            logger.warning(f"Invalid TRANSFER_HOST payload: {e}")
                            await _send_error(
                                ErrorCode.INVALID_PAYLOAD, f"Invalid transfer host payload: {e}"
                            )
                            continue

                        target_nickname = transfer_payload.to_nickname.strip()

                        # Cannot transfer to self
                        if target_nickname == nickname:
                            await _send_error(
                                ErrorCode.CANNOT_TRANSFER_TO_SELF,
                                "Cannot transfer host privileges to yourself.",
                            )
                            continue

                        # Check if target player exists and is connected
                        target_player = await room_service.get_player(
                            redis, room_code, target_nickname
                        )
                        if not target_player:
                            await _send_error(
                                ErrorCode.PLAYER_NOT_FOUND,
                                f"Player '{target_nickname}' not found in room.",
                            )
                            continue

                        if not target_player.connected:
                            await _send_error(
                                ErrorCode.PLAYER_NOT_FOUND,
                                f"Player '{target_nickname}' is not currently connected.",
                            )
                            continue

                        # Update room metadata with new host
                        room_meta_local = await room_service.get_room_meta(redis, room_code)
                        if not room_meta_local:
                            await _send_error(ErrorCode.ROOM_NOT_FOUND, "Room not found.")
                            continue

                        previous_host = room_meta_local.host_nickname
                        room_meta_local.host_nickname = target_nickname
                        room_meta_local.host_disconnected_ts = (
                            None  # Clear any disconnect timestamp
                        )

                        success = await room_service.set_room_meta(
                            redis, room_code, room_meta_local
                        )
                        if not success:
                            await _send_error(
                                ErrorCode.INTERNAL_SERVER_ERROR,
                                "Failed to update room with new host.",
                            )
                            continue

                        # Broadcast newHost message to all players
                        new_host_payload = NewHostPayload(nickname=target_nickname)
                        new_host_message = WSMessage(
                            type=WSMessageType.NEW_HOST, payload=new_host_payload.model_dump()
                        )
                        await conn_manager.broadcast(new_host_message.model_dump(), room_code)

                        logger.info(
                            f"Host transferred from {previous_host} to {target_nickname} in "
                            f"room {room_code}."
                        )

                        # Update local flag - current connection is no longer host
                        is_host = False

                        # Cancel any pending auto-transfer tasks since we have a new host
                        if auto_transfer_host_task and not auto_transfer_host_task.done():
                            auto_transfer_host_task.cancel()
                            auto_transfer_host_task = None

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
                f"Host {nickname} disconnected from room {room_code}. "
                f"Checking for immediate transfer."
            )

            # Check if there are other connected players for immediate transfer
            all_players = await room_service.get_all_players(redis, room_code)
            connected_players = [
                p for p in all_players.values() if p.connected and p.nickname != nickname
            ]

            if connected_players:
                # Immediate transfer to first available player
                new_host = connected_players[0]
                final_room_meta.host_nickname = new_host.nickname
                final_room_meta.host_disconnected_ts = None  # No disconnect timestamp needed
                await room_service.set_room_meta(redis, room_code, final_room_meta)

                # Broadcast newHost message immediately
                new_host_payload = NewHostPayload(nickname=new_host.nickname)
                new_host_message = WSMessage(
                    type=WSMessageType.NEW_HOST, payload=new_host_payload.model_dump()
                )
                await conn_manager.broadcast(new_host_message.model_dump(), room_code)

                logger.info(
                    f"Immediately transferred host from {nickname} to "
                    f"{new_host.nickname} in room {room_code}"
                )
            else:
                # No other players, just record disconnect for future joins
                await _handle_host_disconnect()  # Start timers/allow claim

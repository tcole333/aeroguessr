import asyncio
import json
import logging
import random
import time
from typing import List, Optional

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

from backend.schemas.core import Player, RoomMeta, ScoringMode
from backend.schemas.game import PlayerGuess, RoundResultDetail, RoundStateEnum
from backend.schemas.room import (
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinRequest,
    RoomJoinResponse,
    generate_room_code,
)
from backend.schemas.ws import (
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
    TransferHostPayload,
    WSMessage,
)
from backend.services import room_service, scoring
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# <<< TEMPORARY DEBUGGING >>>
logger.setLevel(logging.DEBUG)
# <<<<<<<<<<<<<<<<<<<<<<<<<<<


# Dependency function to get Redis client
# (Could be moved to a dedicated deps.py file later)
async def get_redis_client() -> RedisClient:
    # This assumes RedisClient can be instantiated directly.
    # If it needs setup (like connecting pool), that should happen elsewhere
    # (e.g., FastAPI lifespan events) and this function would yield the client.
    # For now, direct instantiation works with the current RedisClient structure.
    return RedisClient()


# Create a single instance of the ConnectionManager
manager = ConnectionManager()

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
    redis_client: RedisClient = Depends(get_redis_client),  # noqa: B008
) -> RoomCreateResponse:
    """
    Creates a new game room and registers the host in Redis.

    Args:
        request: The incoming request object (used to build the WS URL).
        room_data: Data for the new room including host nickname, mode, and timeout.
        response: The outgoing response object (used to set Location header).
        redis_client: Injected RedisClient instance.

    Returns:
        The room code and WebSocket URL for the host.

    Raises:
        HTTPException: If a unique room code cannot be generated after several tries.
    """
    max_retries = 5
    for _ in range(max_retries):
        room_code = generate_room_code()
        meta_key = f"room:{room_code}:meta"
        if not await redis_client.exists(meta_key):
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
        await redis_client.set_json(meta_key, new_room_meta, expire_seconds=room_ttl)

        # Use room_service to add the host player
        await room_service.add_player(redis=redis_client, room_code=room_code, player=host_player)
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
    redis_client: RedisClient = Depends(get_redis_client),  # noqa: B008
) -> RoomJoinResponse:
    """
    Allows a player to join an existing room.

    Args:
        request: The incoming request object.
        room_code: The 4-letter code of the room to join.
        join_data: Data containing the player's desired nickname.
        redis_client: Injected RedisClient instance.

    Returns:
        The WebSocket URL for the player to connect to.

    Raises:
        HTTPException (404): If the room_code does not correspond to an active room.
        HTTPException (409): If the chosen nickname is already in use in the room.
        HTTPException (500): If there is an error interacting with Redis.
    """
    meta_key = f"room:{room_code}:meta"
    # players_key = f"room:{room_code}:players"
    room_ttl = 3600  # 1 hour

    # 1. Check if room exists
    if not await redis_client.exists(meta_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Room '{room_code}' not found."
        )

    # 2. Check if nickname is already taken in this room
    # Use room_service to check for existing player
    existing_player = await room_service.get_player(
        redis=redis_client, room_code=room_code, nickname=join_data.nickname
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
        await room_service.add_player(redis=redis_client, room_code=room_code, player=new_player)

        # 4. Refresh TTLs to keep room alive (Only meta TTL needs explicit refresh here)
        # Player hash TTL is handled by add_player
        await redis_client.expire(meta_key, room_ttl)
        # await redis_client.expire(players_key, room_ttl) # No longer needed

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
    redis_client: RedisClient = Depends(get_redis_client),  # noqa: B008
) -> None:
    """Handle WebSocket connections for players in a room using ConnectionManager."""
    meta_key = f"room:{room_code}:meta"
    # players_key = f"room:{room_code}:players"

    # --- Connection Validation (Before accepting) --- #
    room_meta: RoomMeta | None = await redis_client.get_model(meta_key, RoomMeta)
    if not room_meta:
        logger.warning(f"WebSocket connection rejected: Room {room_code} not found.")
        # Close the connection explicitly before returning
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Use room_service to get player data
    player = await room_service.get_player(
        redis=redis_client, room_code=room_code, nickname=nickname
    )
    if not player:
        logger.warning(
            f"WebSocket connection rejected: Player {nickname} not found in room {room_code}. "
            f"(Join endpoint should have created player first)"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Player exists, proceed with connection using the manager
    await manager.connect(websocket, room_code, nickname)

    # Keep track of active background tasks for this connection
    background_tasks = set()

    # --- Round Timer Task --- #
    current_round_timer_task: Optional[asyncio.Task] = None
    # --- Host Transfer Timers --- #
    claim_host_timer_task: Optional[asyncio.Task] = None
    auto_transfer_timer_task: Optional[asyncio.Task] = None

    async def _handle_host_disconnect() -> None:
        """Initiates timers when the host disconnects."""
        nonlocal claim_host_timer_task, auto_transfer_timer_task
        logger.warning(
            f"Host {nickname} disconnected from room {room_code}. Starting transfer timers."
        )

        # Cancel any existing timers (shouldn't happen often, but defensively)
        if claim_host_timer_task and not claim_host_timer_task.done():
            claim_host_timer_task.cancel()
        if auto_transfer_timer_task and not auto_transfer_timer_task.done():
            auto_transfer_timer_task.cancel()

        claim_timeout_s = 120  # 2 minutes
        auto_transfer_timeout_s = 300  # 5 minutes

        async def _allow_claim_host() -> None:
            await asyncio.sleep(claim_timeout_s)
            logger.info(f"Claim host window (2 min) expired for room {room_code}.")
            # Logic after claim window ends (if needed, maybe just rely on auto-transfer)

        async def _auto_transfer_host() -> None:
            await asyncio.sleep(auto_transfer_timeout_s)
            logger.warning(
                f"Auto-transfer timeout (5 min) reached for room {room_code}. Selecting new host."
            )
            # Check if host reconnected in the meantime
            current_meta = await room_service.get_room_meta(redis_client, room_code)
            if not current_meta:
                logger.error(f"Cannot auto-transfer host: Room {room_code} no longer exists.")
                return
            host_player = await room_service.get_player(
                redis_client, room_code, current_meta.host_nickname
            )
            if host_player and host_player.connected:
                logger.info(
                    f"Host {current_meta.host_nickname} reconnected before auto-transfer. Aborting."
                )
                return

            # Select a new host randomly from connected players
            all_players = await room_service.get_all_players(redis_client, room_code)
            connected_players = [
                p
                for p in all_players.values()
                if p.connected and p.nickname != current_meta.host_nickname
            ]
            if not connected_players:
                logger.warning(
                    f"Cannot auto-transfer host in room {room_code}: No other connected players."
                )
                # What happens here? Room might die out naturally?
                return

            new_host = random.choice(connected_players)  # Needs import random
            current_meta.host_nickname = new_host.nickname
            await room_service.set_room_meta(redis_client, room_code, current_meta)
            logger.info(f"Auto-transferring host to {new_host.nickname} in room {room_code}.")

            # Broadcast newHost message
            new_host_payload = NewHostPayload(nickname=new_host.nickname)
            new_host_message = WSMessage(type="newHost", payload=new_host_payload.model_dump())
            await manager.broadcast(new_host_message.model_dump(), room_code)

        claim_host_timer_task = asyncio.create_task(_allow_claim_host())
        auto_transfer_timer_task = asyncio.create_task(_auto_transfer_host())
        background_tasks.add(claim_host_timer_task)
        background_tasks.add(auto_transfer_timer_task)
        claim_host_timer_task.add_done_callback(background_tasks.discard)
        auto_transfer_timer_task.add_done_callback(background_tasks.discard)

    async def _cancel_host_disconnect_timers() -> None:
        """Cancels host disconnect timers if the host reconnects."""
        nonlocal claim_host_timer_task, auto_transfer_timer_task
        if claim_host_timer_task and not claim_host_timer_task.done():
            logger.info(f"Host {nickname} reconnected. Cancelling claim host timer.")
            claim_host_timer_task.cancel()
            claim_host_timer_task = None
        if auto_transfer_timer_task and not auto_transfer_timer_task.done():
            logger.info(f"Host {nickname} reconnected. Cancelling auto-transfer timer.")
            auto_transfer_timer_task.cancel()
            auto_transfer_timer_task = None

    async def _end_round(initiator: str = "timer") -> None:
        """Handles scoring, result broadcast, and state transition at round end."""
        nonlocal current_round_timer_task  # Allow modification
        logger.info(f"Attempting to end round for room {room_code}, initiated by {initiator}.")

        # Prevent multiple simultaneous ends (e.g., timer and last guess)
        # This requires careful state management or locking if truly concurrent
        # For now, assume get/set is fast enough for typical race conditions
        round_data = await room_service.get_round_data(redis_client, room_code)
        if not round_data or round_data.state != RoundStateEnum.ACCEPTING_GUESSES:
            logger.warning(
                (
                    f"_end_round called for room {room_code} but state is "
                    f"{round_data.state if round_data else 'N/A'}. Ignoring."
                )
            )
            # Cancel timer if it's still running but state changed unexpectedly
            if current_round_timer_task and not current_round_timer_task.done():
                current_round_timer_task.cancel()
            return

        # Cancel the timer task if it exists and isn't the initiator
        if (
            initiator != "timer"
            and current_round_timer_task
            and not current_round_timer_task.done()
        ):
            logger.debug(f"Round ended early by {initiator}, cancelling timer task.")
            current_round_timer_task.cancel()
            current_round_timer_task = None  # Clear reference

        # --- Scoring --- #
        logger.info(
            f"Ending round {round_data.round_number} for room {room_code}. Calculating scores."
        )
        results: List[RoundResultDetail] = []
        all_players = await room_service.get_all_players(redis_client, room_code)
        correct_code = round_data.correct_airport_code
        room_meta_local = await room_service.get_room_meta(
            redis_client, room_code
        )  # Fetch fresh meta for scoring mode

        if not room_meta_local:
            logger.error(f"Cannot end round: RoomMeta not found for {room_code}")
            # Transition to waiting? Or handle error differently?
            round_data.state = RoundStateEnum.WAITING_FOR_SELECTION
            await room_service.set_round_data(redis_client, room_code, round_data)
            return

        if not correct_code:
            logger.error(
                (
                    f"Cannot end round: Correct airport code not set for "
                    f"round {round_data.round_number} in {room_code}"
                )
            )
            round_data.state = RoundStateEnum.WAITING_FOR_SELECTION
            await room_service.set_round_data(redis_client, room_code, round_data)
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
                        redis=redis_client,
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
        await room_service.set_round_data(redis_client, room_code, round_data)

        # Broadcast roundResult message
        result_payload = RoundResultPayload(results=results)
        result_message = WSMessage(type="roundResult", payload=result_payload.model_dump())
        await manager.broadcast(result_message.model_dump(), room_code)
        logger.info(
            f"Broadcasted roundResult for round {round_data.round_number} in room {room_code}."
        )

        # Broadcast score updates via delta message if any scores changed
        if updated_scores_delta:
            delta_scores = {"scores": updated_scores_delta}
            delta_message = WSMessage(type="delta", payload=delta_scores)
            await manager.broadcast(delta_message.model_dump(), room_code)
            logger.debug(f"Broadcasted score delta for room {room_code}: {updated_scores_delta}")

        # TODO: Add logic/timer to transition from SHOWING_RESULTS back to WAITING_FOR_SELECTION
        # For now, host must manually start next round?
        # Maybe start a short task here?
        async def _reset_for_next_round(delay: int = 5) -> None:
            await asyncio.sleep(delay)
            rd = await room_service.get_round_data(redis_client, room_code)
            if rd and rd.state == RoundStateEnum.SHOWING_RESULTS:
                logger.info(f"Resetting state to WAITING_FOR_SELECTION for room {room_code}")
                rd.state = RoundStateEnum.WAITING_FOR_SELECTION
                rd.selected_plane_hex = None
                rd.correct_airport_code = None
                rd.guess_direction = None
                rd.round_start_time = None
                rd.guesses = {}
                rd.results = None
                await room_service.set_round_data(redis_client, room_code, rd)
                # Maybe broadcast a state update?

        reset_task = asyncio.create_task(_reset_for_next_round())
        background_tasks.add(reset_task)
        reset_task.add_done_callback(background_tasks.discard)

    # --- WebSocket Endpoint Main Logic --- #

    # Helper function to send error messages
    async def _send_error(code: str, message: str) -> None:
        logger.warning(f"Sending error to {nickname}: [{code}] {message}")
        error_payload = ErrorPayload(code=code, message=message)
        error_message = WSMessage(type="error", payload=error_payload.model_dump())
        try:
            await manager.send_personal_message(error_message.model_dump(), websocket)
        except WebSocketDisconnect:
            # Already disconnected, can't send error
            pass
        except Exception as e:
            logger.error(f"Failed to send error message to {nickname}: {e}")

    # Initialize round data on connect if it doesn't exist
    try:
        current_round_data = await room_service.initialize_round_data(redis_client, room_code)
        logger.info(
            (
                f"Ensured round data exists for room {room_code}. Current state: "
                f"{current_round_data.state}"
            )
        )
    except Exception as e:
        logger.error((f"Failed to initialize round data for room {room_code}: {e}, disconnecting."))
        await manager.disconnect(websocket, room_code, nickname)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    # Get RoomMeta once - needed for host checks and timeout
    # Add get_room_meta helper to room_service
    room_meta = await room_service.get_room_meta(redis_client, room_code)
    if not room_meta:
        logger.error(
            (f"RoomMeta not found for {room_code} " f"during connection setup. Disconnecting.")
        )
        await manager.disconnect(websocket, room_code, nickname)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Update player status using room_service
    updated_player = await room_service.update_player_status(
        redis=redis_client, room_code=room_code, nickname=nickname, connected=True
    )
    if not updated_player:
        # Should not happen if initial get_player succeeded, but handle defensively
        logger.error((f"Failed to update status for connecting player {nickname}, disconnecting."))
        await manager.disconnect(websocket, room_code, nickname)  # Use the manager's disconnect
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        return

    player = updated_player  # Use the updated player object going forward

    # If the host reconnected, cancel any pending transfer timers
    if nickname == room_meta.host_nickname:
        await _cancel_host_disconnect_timers()

    # Broadcast playerJoined message to others in the room
    join_payload = PlayerJoinedPayload(nickname=nickname)
    join_message = WSMessage(type="playerJoined", payload=join_payload.model_dump())
    await manager.broadcast(join_message.model_dump(), room_code, exclude_nickname=nickname)

    # Send initial state sync to the newly connected player
    # Use room_service to get all players
    all_players_dict = await room_service.get_all_players(redis=redis_client, room_code=room_code)
    sync_message = WSMessage(
        type="stateSync",
        payload=FullRoomState(
            room_meta=room_meta,
            players=all_players_dict,
            # TODO: Add round state later
        ).model_dump(),
        ts=int(time.time() * 1000),
    )
    try:
        await manager.send_personal_message(sync_message.model_dump(), websocket)
    except WebSocketDisconnect:
        # If sending initial sync fails, disconnect immediately
        logger.warning(f"Could not send initial stateSync to {nickname}, disconnecting.")
        manager.disconnect(room_code, nickname)  # Disconnect from manager

        # Update player status using room_service
        await room_service.update_player_status(
            redis=redis_client, room_code=room_code, nickname=nickname, connected=False
        )

        # Broadcast playerLeft message to others in the room
        left_payload = PlayerLeftPayload(nickname=nickname)
        left_message = WSMessage(type="playerLeft", payload=left_payload.model_dump())
        await manager.broadcast(left_message.model_dump(), room_code, exclude_nickname=nickname)
        return  # Exit the endpoint function

    # --- Heartbeat and Message Handling --- #
    last_pong_time = time.time()
    pong_timeout_s = 30  # 3 missed pings at 10s interval

    async def _recv_loop(ws: WebSocket) -> None:
        nonlocal last_pong_time
        nonlocal current_round_timer_task
        try:
            while True:
                # In httpx-ws / ASGI test transports a close frame surfaces as
                # RuntimeError("Expected ASGI message 'websocket.receive' …
                # got 'websocket.close'").
                # Convert that to the canonical WebSocketDisconnect so our
                # upper-level flow treats it as a normal disconnect.
                try:
                    data = await ws.receive_text()
                except RuntimeError as exc:
                    # Starlette translates close frames to RuntimeError in
                    # test context; use generic close code 1000 (normal).
                    raise WebSocketDisconnect(code=status.WS_1000_NORMAL_CLOSURE) from exc
                message_data = json.loads(data)
                message = WSMessage(**message_data)
                logger.debug(f"Received WS message from {nickname}: {message.type}")

                if message.type == "pong":
                    # Validate pong payload if needed (e.g., matching seq)
                    last_pong_time = time.time()
                elif message.type == "ping":
                    # Respond immediately to client ping if needed
                    pong_payload = PingPongPayload(seq=message.payload.get("seq", 0))
                    await manager.send_personal_message(
                        WSMessage(
                            type="pong",
                            payload=pong_payload.model_dump(),
                            ts=int(time.time() * 1000),
                        ).model_dump(),
                        ws,
                    )
                # --- Host Actions --- #
                elif message.type == "selectPlane":
                    if nickname != room_meta.host_nickname:
                        await _send_error("NOT_HOST", "Only the host can select a plane.")
                        continue

                    try:
                        payload = SelectPlanePayload(**message.payload)
                        plane_hex = payload.hex
                    except ValidationError as e:
                        await _send_error("INVALID_PAYLOAD", f"Invalid selectPlane payload: {e}")
                        continue

                    current_round_data = await room_service.get_round_data(redis_client, room_code)
                    if not current_round_data:
                        await _send_error(
                            "ROUND_DATA_MISSING", "Internal error: Round data not found."
                        )
                        continue  # Or raise?
                    if current_round_data.state != RoundStateEnum.WAITING_FOR_SELECTION:
                        await _send_error(
                            "INVALID_STATE",
                            f"Cannot select plane, current round state is "
                            f"{current_round_data.state}.",
                        )
                        continue

                    # --- Fetch Plane Data (Placeholder Implementation) --- #
                    # TODO: Replace placeholder with actual plane data lookup and origin/dest logic
                    #       Requires PlaneState schema and potentially flight phase analysis.
                    plane_key = f"plane:{plane_hex}"
                    if not await redis_client.exists(plane_key):
                        await _send_error(
                            "PLANE_NOT_FOUND",
                            f"Selected plane {plane_hex} not found in tracking data.",
                        )
                        continue

                    # Placeholder logic from TECH_DEBT.md
                    correct_airport_code = "BOS"  # Hardcoded
                    guess_direction = "destination"  # Hardcoded
                    logger.warning(
                        f"Using placeholder logic for selectPlane: "
                        f"Correct={correct_airport_code}, Dir={guess_direction}"
                    )
                    # ---------------------------------------------------- #

                    current_round_data.selected_plane_hex = plane_hex
                    current_round_data.correct_airport_code = correct_airport_code
                    current_round_data.guess_direction = guess_direction
                    # Keep state as WAITING_FOR_SELECTION until startRound
                    # current_round_data.state = RoundStateEnum.PLANE_SELECTED # Add if needed

                    await room_service.set_round_data(redis_client, room_code, current_round_data)
                    logger.info(
                        f"Host {nickname} selected plane {plane_hex} for room {room_code}. "
                        f"Correct: {correct_airport_code}, Direction: {guess_direction}."
                    )
                    # Optional: Send confirmation back to host?
                    # confirm_payload = PlaneSelectedConfirmPayload(...)
                    # await manager.send_personal_message(...)

                elif message.type == "startRound":
                    if nickname != room_meta.host_nickname:
                        await _send_error("NOT_HOST", "Only the host can start a round.")
                        continue

                    current_round_data = await room_service.get_round_data(redis_client, room_code)
                    # Verify state and that a plane is selected
                    if not current_round_data:
                        await _send_error(
                            "ROUND_DATA_MISSING", "Internal error: Round data not found."
                        )
                        continue
                    if current_round_data.state != RoundStateEnum.WAITING_FOR_SELECTION:
                        await _send_error(
                            "INVALID_STATE",
                            f"Cannot start round, current state is {current_round_data.state}.",
                        )
                        continue
                    if not current_round_data.selected_plane_hex:
                        await _send_error("PLANE_NOT_SELECTED", "A plane must be selected first.")
                        continue

                    # --- Update Round State --- #
                    current_round_data.state = RoundStateEnum.ACCEPTING_GUESSES
                    current_round_data.round_start_time = time.time()
                    current_round_data.guesses = {}  # Clear previous guesses
                    current_round_data.results = None  # Clear previous results
                    current_round_data.round_number += 1  # Increment round number

                    await room_service.set_round_data(redis_client, room_code, current_round_data)
                    logger.info(
                        f"Host {nickname} started round {current_round_data.round_number} "
                        f"for plane {current_round_data.selected_plane_hex} in room {room_code}."
                    )

                    # --- Broadcast roundStart --- #
                    round_start_payload = RoundStartPayload(
                        hex=current_round_data.selected_plane_hex,
                        timeout_s=room_meta.round_timeout_seconds,
                        direction=current_round_data.guess_direction,
                        round_number=current_round_data.round_number,
                    )
                    round_start_message = WSMessage(
                        type="roundStart", payload=round_start_payload.model_dump()
                    )
                    await manager.broadcast(round_start_message.model_dump(), room_code)

                    # --- Start Round Timer --- #
                    # Cancel existing timer if any (e.g., from a previous partial round)
                    if current_round_timer_task and not current_round_timer_task.done():
                        current_round_timer_task.cancel()

                    timer_duration = room_meta.round_timeout_seconds
                    logger.info(f"Starting round timer for {timer_duration}s in room {room_code}.")

                    async def _round_timer_ends(timer_duration: int) -> None:
                        await asyncio.sleep(timer_duration)
                        logger.info(f"Round timer expired for room {room_code}. Ending round.")
                        await _end_round(initiator="timer")

                    current_round_timer_task = asyncio.create_task(
                        _round_timer_ends(timer_duration)
                    )
                    background_tasks.add(current_round_timer_task)
                    # Callback to remove task from set when done/cancelled
                    current_round_timer_task.add_done_callback(background_tasks.discard)

                elif message.type == "transferHost":
                    if nickname != room_meta.host_nickname:
                        logger.warning((f"Player {nickname} (not host) tried to transfer host."))
                        await _send_error("NOT_HOST", "Only the host can transfer the host role.")
                        continue
                    try:
                        payload = TransferHostPayload(**message.payload)
                        target_nickname = payload.to_nickname
                        if nickname == target_nickname:
                            await _send_error("INVALID_TARGET", "Cannot transfer host to yourself.")
                            continue
                        # Validate target player exists and is connected
                        target_player = await room_service.get_player(
                            redis_client, room_code, target_nickname
                        )
                        if not target_player or not target_player.connected:
                            logger.warning(
                                (
                                    f"Host {nickname} tried to transfer host to "
                                    f"invalid/disconnected player {target_nickname}."
                                )
                            )
                            await _send_error(
                                "TARGET_NOT_FOUND",
                                f"Player '{target_nickname}' not found or not connected.",
                            )
                            continue

                        # Update RoomMeta
                        room_meta.host_nickname = target_nickname
                        await room_service.set_room_meta(redis_client, room_code, room_meta)
                        logger.info(
                            (
                                f"Host {nickname} transferred host role to {target_nickname} in "
                                f"room {room_code}."
                            )
                        )

                        # Broadcast newHost message
                        new_host_payload = NewHostPayload(nickname=target_nickname)
                        new_host_message = WSMessage(
                            type="newHost", payload=new_host_payload.model_dump()
                        )
                        await manager.broadcast(new_host_message.model_dump(), room_code)

                    except ValidationError as e:
                        logger.warning(f"Invalid transferHost payload from {nickname}: {e}")
                        await _send_error("INVALID_PAYLOAD", f"Invalid message format: {e}")
                    except Exception as e:
                        logger.error(
                            f"Error processing transferHost from {nickname}: {e}", exc_info=True
                        )
                        await _send_error("INTERNAL_ERROR", "An unexpected error occurred.")

                elif message.type == "claimHost":
                    if not claim_host_timer_task or claim_host_timer_task.done():
                        logger.warning(
                            f"Player {nickname} tried to claim host, but claim window not active."
                        )
                        await _send_error(
                            "CLAIM_WINDOW_CLOSED", "The host claim window is not active."
                        )
                        continue

                    # TODO: Refine check - need to know if 2 minutes have passed.
                    # This requires the timer task to signal completion differently.

                    try:
                        # Ensure the current host is actually disconnected
                        current_meta = await room_service.get_room_meta(redis_client, room_code)
                        if not current_meta:
                            raise Exception("Room metadata not found during claimHost.")
                        if nickname == current_meta.host_nickname:
                            await _send_error("ALREADY_HOST", "You are already the host.")
                            continue

                        original_host_player = await room_service.get_player(
                            redis_client, room_code, current_meta.host_nickname
                        )
                        if original_host_player and original_host_player.connected:
                            logger.warning(
                                (
                                    f"Player {nickname} tried to claim host, but original "
                                    f"host {current_meta.host_nickname} is connected."
                                )
                            )
                            await _send_error(
                                "HOST_CONNECTED",
                                "Cannot claim host, the original host is connected.",
                            )
                            continue

                        # Make the current player the new host
                        new_host_nickname = nickname
                        current_meta.host_nickname = new_host_nickname
                        await room_service.set_room_meta(redis_client, room_code, current_meta)
                        logger.info(
                            (
                                f"Player {nickname} successfully claimed host role in room "
                                f"{room_code}."
                            )
                        )

                        # Cancel the host transfer timers
                        await _cancel_host_disconnect_timers()

                        # Broadcast newHost message
                        new_host_payload = NewHostPayload(nickname=new_host_nickname)
                        new_host_message = WSMessage(
                            type="newHost", payload=new_host_payload.model_dump()
                        )
                        await manager.broadcast(new_host_message.model_dump(), room_code)

                    except Exception as e:
                        logger.error(
                            f"Error processing claimHost from {nickname}: {e}", exc_info=True
                        )
                        await _send_error(
                            "INTERNAL_ERROR", "An unexpected error occurred claiming host."
                        )

                # --- Player Actions --- #
                elif message.type == "guess":
                    try:
                        payload = GuessPayload(**message.payload)
                        # <<< ADD Log before get >>>
                        logger.info(f"[HANDLER DEBUG] Attempting to get round data for {room_code}")
                        current_round_data = await room_service.get_round_data(
                            redis_client, room_code
                        )
                        # <<< ADD Log after get >>>
                        logger.info(
                            f"[HANDLER DEBUG] Got round data for {room_code}: {current_round_data}"
                        )

                        if (
                            not current_round_data
                            or current_round_data.state != RoundStateEnum.ACCEPTING_GUESSES
                        ):
                            # <<< ADD Log before state error >>>
                            logger.warning(
                                f"[HANDLER DEBUG] Guess rejected for {nickname}. Current state: "
                                f"{current_round_data.state if current_round_data else 'None'}"
                            )
                            await _send_error(
                                "GUESS_OUTSIDE_ROUND",
                                "Guesses are only allowed during an active round.",
                            )
                            continue
                        if nickname in current_round_data.guesses:
                            await _send_error(
                                "DUPLICATE_GUESS",
                                "You have already submitted a guess for this round.",
                            )
                            continue

                        # Store the guess
                        new_guess = PlayerGuess(nickname=nickname, guess=payload.airport_code)
                        current_round_data.guesses[nickname] = new_guess

                        logger.info(
                            f"[HANDLER DEBUG] About to call set_round_data for {nickname}. "
                            f"Guesses in object: {current_round_data.guesses}"
                        )

                        # Save the updated round data using the service function
                        success = await room_service.set_round_data(
                            redis_client, room_code, current_round_data
                        )

                        # Log success or failure of the service call
                        if not success:
                            # This indicates an issue within set_round_data or Redis interaction
                            logger.error(
                                f"FAILED to save guess for {nickname} using "
                                f"room_service.set_round_data."
                            )
                            # Consider sending an error back to the user?
                            await _send_error(
                                "SAVE_ERROR", "Failed to record your guess. Please try again."
                            )
                            continue  # Skip the rest of the guess processing if save failed

                        # Existing info log remains
                        logger.info(
                            f"Player {nickname} guessed '{payload.airport_code}' for "
                            f"round {current_round_data.round_number}."
                        )

                        # Check if all connected players have guessed to end round early
                        all_players_in_room = await room_service.get_all_players(
                            redis_client, room_code
                        )
                        connected_players = {
                            p.nickname for p in all_players_in_room.values() if p.connected
                        }
                        guessed_players = set(current_round_data.guesses.keys())

                        # Ensure the current player is considered connected for this check
                        connected_players.add(nickname)

                        if connected_players.issubset(guessed_players):
                            logger.info(
                                f"All {len(connected_players)} connected players have "
                                f"guessed in room {room_code}. Ending round early."
                            )
                            # Ensure _end_round is called safely from the loop
                            end_task = asyncio.create_task(_end_round(initiator="all_guessed"))
                            background_tasks.add(end_task)
                            end_task.add_done_callback(background_tasks.discard)
                        else:
                            logger.debug(
                                f"Waiting for more guesses. Connected: {len(connected_players)}, "
                                f"Guessed: {len(guessed_players)} ({guessed_players})"
                            )

                    except ValidationError as e:
                        await _send_error("INVALID_PAYLOAD", f"Invalid guess format: {e}")
                    except Exception as e:
                        logger.error(f"Error processing guess from {nickname}: {e}", exc_info=True)
                        await _send_error(
                            "INTERNAL_ERROR", "An error occurred submitting your guess."
                        )

                elif message.type == "leave":
                    logger.info(f"Leave received from {nickname}")
                    # Graceful client-initiated disconnect – close socket and exit recv loop
                    await ws.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
                # TODO: Add handlers for other message types (selectPlane, startRound, etc.)

                # Update last seen timestamp on any valid message using room_service
                # We only need to update last_seen, connected status remains True here
                # Optimization: Consider updating last_seen less frequently if needed.
                updated_player = await room_service.get_player(
                    redis=redis_client, room_code=room_code, nickname=nickname
                )
                if updated_player:
                    updated_player.last_seen_ts = time.time()
                    await room_service.add_player(
                        redis=redis_client, room_code=room_code, player=updated_player
                    )
                    player = updated_player  # Keep local player object in sync # noqa: F841
                else:
                    logger.warning(
                        f"Player {nickname} not found during activity update, may disconnect."
                    )
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR)
                    break

        except WebSocketDisconnect:
            logger.info(f"Receive loop: WebSocket disconnected for {nickname}")
            # Ensure manager is updated immediately on detected disconnect
            manager.disconnect(room_code, nickname)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON received from {nickname}")
            # Decide whether to disconnect on bad data
        except Exception as e:
            logger.error(f"Error in WebSocket receive loop for {nickname}: {e}")
            # Ensure manager is updated on unexpected errors leading to loop exit
            manager.disconnect(room_code, nickname)
            # Consider re-raising or specific handling

    async def send_pings(ws: WebSocket) -> None:
        ping_interval_s = 10
        seq = 0
        try:
            while True:
                await asyncio.sleep(ping_interval_s)
                if time.time() - last_pong_time > pong_timeout_s:
                    logger.warning(
                        (
                            f"WebSocket timeout: No pong received from {nickname} for "
                            f"{pong_timeout_s}s. Closing connection."
                        )
                    )
                    # Close the WebSocket from the server side
                    await ws.close(code=status.WS_1008_POLICY_VIOLATION)
                    # Manager disconnect will be handled by the finally block or
                    #  receive loop exception
                    break  # Exit ping loop

                seq += 1
                ping_payload = PingPongPayload(seq=seq)
                ping_message = WSMessage(
                    type="ping", payload=ping_payload.model_dump(), ts=int(time.time() * 1000)
                )
                try:
                    # Check WebSocket state before attempting to send
                    if (
                        ws.application_state != WebSocketState.CONNECTED
                        or ws.client_state != WebSocketState.CONNECTED
                    ):
                        logger.debug(
                            f"Pinger loop: WebSocket no longer connected for {nickname}. "
                            "Exiting pinger."
                        )
                        break  # Exit loop gracefully if socket is closed

                    await manager.send_personal_message(ping_message.model_dump(), ws)
                except WebSocketDisconnect:
                    logger.info(
                        f"Pinger loop: WebSocket disconnected for {nickname} while " "sending ping."
                    )
                    # Manager disconnect will be handled by the finally block or
                    #  receive loop exception
                    break  # Exit ping loop
        except asyncio.CancelledError:
            logger.info(f"Pinger task cancelled for {nickname}")
        except Exception as e:
            logger.error(f"Error in WebSocket pinger loop for {nickname}: {e}")
            # Ensure manager is updated if pinger crashes unexpectedly
            # Check state before attempting disconnect, as it might already be handled
            if nickname in manager.get_room_connections(room_code):
                manager.disconnect(room_code, nickname)
            # Consider closing the websocket here as well
            try:
                # Check state again before closing
                if ws.application_state == WebSocketState.CONNECTED:
                    await ws.close(code=status.WS_1011_INTERNAL_ERROR)
            except Exception:  # Ignore errors during close
                pass

    # Add the pinger task to the background tasks set
    # Create the background task for sending pings
    ping_task = asyncio.create_task(send_pings(websocket))
    # Add the task to the set for tracking cancellation during cleanup
    background_tasks.add(ping_task)
    # Optional but recommended: remove task from set upon completion/cancellation
    ping_task.add_done_callback(background_tasks.discard)

    try:
        await _recv_loop(websocket)  # blocks until disconnect / error
    except WebSocketDisconnect:
        # This exception is often caught inside _recv_loop or send_pings first
        logger.info(f"WebSocket disconnected event caught for {nickname}.")
    except Exception as e:  # <-- Restore this general exception handler
        logger.error(
            f"Unexpected error in WebSocket handler for {nickname} in {room_code}: {e}",
            exc_info=True,
        )
        # Attempt to send error message if socket still open
        # Check state defensively before sending
        if (
            websocket.application_state == WebSocketState.CONNECTED
            and websocket.client_state == WebSocketState.CONNECTED
        ):
            await _send_error("UNEXPECTED_ERROR", f"An internal error occurred: {e}")
    finally:
        logger.info(f"Cleaning up WebSocket connection for {nickname} in room {room_code}")

        # Cancel any outstanding background tasks for this player
        logger.debug(f"Cancelling {len(background_tasks)} background tasks for {nickname}.")
        for task in list(background_tasks):  # Iterate over a copy
            if not task.done():
                task.cancel()
        # Give cancelled tasks a chance to run finally blocks
        if background_tasks:
            await asyncio.gather(*background_tasks, return_exceptions=True)
            logger.debug(f"Finished awaiting cancelled tasks for {nickname}.")

        # Check if the player is still considered connected by the manager *before*
        # trying to disconnect again
        if nickname in manager.get_room_connections(room_code):
            logger.debug(f"Performing manager disconnect for {nickname} during final cleanup.")
            manager.disconnect(room_code, nickname)  # Call manager disconnect only if needed

            # Also perform Redis status update only if manager disconnect was just done
            try:
                updated = await room_service.update_player_status(
                    redis=redis_client, room_code=room_code, nickname=nickname, connected=False
                )
                if updated:
                    logger.info(
                        f"Updated player {nickname} status to disconnected in Redis "
                        "during final cleanup."
                    )
                    # Broadcast playerLeft only if the player was successfully marked
                    # disconnected here
                    player_left_payload = PlayerLeftPayload(nickname=nickname)
                    left_message = WSMessage(type="playerLeft", payload=player_left_payload)
                    await manager.broadcast(
                        message=left_message.model_dump(exclude_none=True),
                        room_code=room_code,
                        exclude_nickname=nickname,  # Don't send to the player who just left
                    )
                else:
                    # This case might happen if Redis data was removed between check and
                    # update, or if update_player_status failed
                    logger.warning(
                        f"Player {nickname} status not updated in Redis during final cleanup "
                        "(maybe already removed or error)."
                    )

            except Exception as e:
                logger.error(
                    f"Error during final Redis status update or broadcast for {nickname}: {e}",
                    exc_info=True,
                )
        else:
            logger.debug(
                f"Player {nickname} already disconnected by manager, skipping final disconnect "
                "actions."
            )


# --- Background Task: Ping ---

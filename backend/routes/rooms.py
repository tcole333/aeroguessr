import asyncio
import contextlib
import json
import logging
import time

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
from starlette.websockets import WebSocketState

from backend.schemas.core import Player, RoomMeta
from backend.schemas.room import (
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinRequest,
    RoomJoinResponse,
    generate_room_code,
)
from backend.schemas.ws import (
    FullRoomState,
    PingPongPayload,
    PlayerJoinedPayload,
    PlayerLeftPayload,
    WSMessage,
)
from backend.utils.connection_manager import ConnectionManager
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)


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
    players_key = f"room:{room_code}:players"
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
        # Store room metadata
        await redis_client.set_json(meta_key, new_room_meta, expire_seconds=room_ttl)

        # Store host player data in the players hash
        await redis_client.hset_model(players_key, room_data.host_nickname, host_player)
        # Set TTL on the players hash itself
        await redis_client.expire(players_key, room_ttl)

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
    players_key = f"room:{room_code}:players"
    room_ttl = 3600  # 1 hour

    # 1. Check if room exists
    if not await redis_client.exists(meta_key):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Room '{room_code}' not found."
        )

    # 2. Check if nickname is already taken in this room
    existing_player = await redis_client.hget_model(players_key, join_data.nickname, Player)
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
        await redis_client.hset_model(players_key, join_data.nickname, new_player)

        # 4. Refresh TTLs to keep room alive
        await redis_client.expire(meta_key, room_ttl)
        await redis_client.expire(players_key, room_ttl)

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
    players_key = f"room:{room_code}:players"

    # --- Connection Validation (Before accepting) --- #
    room_meta: RoomMeta | None = await redis_client.get_model(meta_key, RoomMeta)
    if not room_meta:
        logger.warning(f"WebSocket connection rejected: Room {room_code} not found.")
        # Close the connection explicitly before returning
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    player: Player | None = await redis_client.hget_model(players_key, nickname, Player)
    if not player:
        logger.warning(
            f"WebSocket connection rejected: Player {nickname} not found in room {room_code}. "
            f"(Join endpoint should have created player first)"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Player exists, proceed with connection using the manager
    await manager.connect(websocket, room_code, nickname)

    # Update player status in Redis to connected=True
    player.connected = True
    player.last_seen_ts = time.time()
    await redis_client.hset_model(players_key, nickname, player)
    # Broadcast playerJoined message to others in the room
    join_payload = PlayerJoinedPayload(nickname=nickname)
    join_message = WSMessage(type="playerJoined", payload=join_payload.model_dump())
    await manager.broadcast(join_message.model_dump(), room_code, exclude_nickname=nickname)

    # Send initial state sync to the newly connected player
    all_players_dict = await redis_client.hgetall_models(players_key, Player)
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
        player.connected = False
        await redis_client.hset_model(players_key, nickname, player)  # Update Redis
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
        try:
            while True:
                # In httpx-ws / ASGI test transports a close frame surfaces as
                # RuntimeError("Expected ASGI message 'websocket.receive' … got 'websocket.close'").
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
                elif message.type == "guess":
                    logger.info(f"Guess received from {nickname}: {message.payload}")
                    # TODO: Process guess (placeholder)
                    # Example: Broadcast delta back (temporary)
                    delta_msg = WSMessage(
                        type="delta",
                        payload={"guess_ack": message.payload, "sender": nickname},
                        ts=int(time.time() * 1000),
                    )
                    await manager.broadcast(
                        delta_msg.model_dump(), room_code, exclude_nickname=nickname
                    )
                elif message.type == "leave":
                    logger.info(f"Leave received from {nickname}")
                    # Graceful client-initiated disconnect – close socket and exit recv loop
                    await ws.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
                # TODO: Add handlers for other message types (selectPlane, startRound, etc.)

                # Update last seen timestamp on any valid message
                player.last_seen_ts = time.time()
                await redis_client.hset_model(players_key, nickname, player)

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
            manager.disconnect(room_code, nickname)
            # Consider closing the websocket here as well
            try:
                await ws.close(code=status.WS_1011_INTERNAL_ERROR)
            except Exception:  # Ignore errors during close
                pass

    # Run receive loop in *current* task to simplify cancellation semantics.
    ping_task = asyncio.create_task(send_pings(websocket))

    try:
        await _recv_loop(websocket)  # blocks until disconnect / error
    finally:
        # Ensure ping task is cancelled regardless of exit reason
        if not ping_task.done():
            ping_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ping_task

    # --- Final cleanup (after loops) --- #
    try:
        # This block ensures cleanup happens regardless of how the connection closes
        logger.info(f"Cleaning up WebSocket connection for {nickname} in room {room_code}")
        # ping_task already cancelled above

        # Attempt graceful close handshake if socket still open
        with contextlib.suppress(Exception):
            if websocket.application_state == WebSocketState.CONNECTED:
                await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)

        # Disconnect from the manager
        manager.disconnect(room_code, nickname)

        # Update player status in Redis to disconnected=False
        # Check if player still exists before updating (might have been removed)
        final_player_check = await redis_client.hget_model(players_key, nickname, Player)
        if final_player_check:
            final_player_check.connected = False
            # last_seen_ts is already updated by receive loop
            await redis_client.hset_model(players_key, nickname, final_player_check)
            # Broadcast playerLeft message to others in the room
            left_payload = PlayerLeftPayload(nickname=nickname)
            left_message = WSMessage(type="playerLeft", payload=left_payload.model_dump())
            await manager.broadcast(left_message.model_dump(), room_code, exclude_nickname=nickname)
        else:
            logger.warning(f"Player {nickname} was already removed from Redis during cleanup.")

    except Exception as e:
        logger.error(f"Error in WebSocket cleanup for {nickname}: {e}")
        # Ensure manager is updated on unexpected errors leading to loop exit
        manager.disconnect(room_code, nickname)
        # Consider re-raising or specific handling

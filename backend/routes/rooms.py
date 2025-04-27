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

from backend.schemas.core import Player, RoomMeta
from backend.schemas.room import (
    RoomCreateRequest,
    RoomCreateResponse,
    RoomJoinRequest,
    RoomJoinResponse,
    generate_room_code,
)
from backend.schemas.ws import FullRoomState, WSMessage
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
    """Handle WebSocket connections for players in a room."""
    meta_key = f"room:{room_code}:meta"
    players_key = f"room:{room_code}:players"

    # --- Connection Handling --- #
    # 1. Check if room exists
    room_meta: RoomMeta | None = await redis_client.get_model(meta_key, RoomMeta)
    if not room_meta:
        logger.warning(f"WebSocket connection rejected: Room {room_code} not found.")
        # Don't accept the connection if the room doesn't exist
        # Client should have received 404 from join/create endpoint
        # We could send a close frame here, but simplest is just not accepting.
        return

    # 2. Check if player exists and handle connection status
    player: Player | None = await redis_client.hget_model(players_key, nickname, Player)
    if not player:
        logger.warning(
            f"WebSocket connection rejected: Player {nickname} not found in room {room_code}. "
            f"Did they join?"
        )
        return

    # TODO: Handle case where player might already have an active connection
    # This might require a ConnectionManager (Task 32)

    await websocket.accept()
    logger.info(f"WebSocket connected: Room={room_code}, Nickname={nickname}")

    # Update player status in Redis
    player.connected = True
    player.last_seen_ts = time.time()  # Use standard epoch seconds for internal logic
    await redis_client.hset_model(players_key, nickname, player)
    # TODO: Broadcast playerJoined event to other clients?

    # --- Send Initial State Sync (Task 30) --- #
    # For now, send mock/example data derived from current state if possible
    # In future, fetch actual current full state
    players_in_room = await redis_client.hgetall_models(players_key, Player)

    sync_payload = FullRoomState(
        room_meta=room_meta,
        players=players_in_room,
        # mock round info if needed
    )
    sync_message = WSMessage(type="stateSync", payload=sync_payload)
    await websocket.send_json(sync_message.model_dump())
    logger.info(f"Sent stateSync to {nickname}")

    # --- Main Message Loop --- #
    try:
        while True:
            # Wait for messages from the client
            data = await websocket.receive_text()  # Or receive_json
            logger.debug(f"Received message from {nickname}: {data}")
            # Process incoming messages (Task 33: guess, Task 39: selectPlane, etc.)
            # Example echo:
            # await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: Room={room_code}, Nickname={nickname}")
        # Update player status in Redis
        if player:
            player.connected = False
            player.last_seen_ts = time.time()
            try:
                await redis_client.hset_model(players_key, nickname, player)
            except Exception as redis_e:
                logger.error(
                    f"Failed to update player {nickname} status on disconnect in Redis: {redis_e}"
                )
        # TODO: Broadcast playerLeft event?
        # Handle host disconnect logic (Task 41)
    except Exception as e:
        logger.error(f"WebSocket error for {nickname}: {e}")
        # Ensure connection is closed gracefully
        # Check if websocket is still open before trying to close
        if websocket.client_state != status.WS_1006_ABNORMAL_CLOSURE:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)

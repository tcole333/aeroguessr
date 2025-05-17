<!-- Solo Mode Feature Specification -->

### Goal

Implement a **Solo Mode** for the Plane Guessing Game, allowing a single player to join a special room, select any displayed aircraft, and guess its origin or destination immediately, without the structured round-based gameplay of multiplayer rooms.

### Alignment with PRD

This feature directly implements **Section 3.2 "Single-player mode"** of the Product Requirements Document (`docs/PRD.md`):

> "Joining the reserved room code `solo` creates a personal room with no round logic—players click any plane and submit guesses immediately."

Scoring will follow the rules in **Section 3.3 "Scoring"** of the PRD.

### Deliverables

1.  **Pydantic Models (`backend/schemas/`)**:

    - Minimal changes to existing models.
    - `backend/schemas/ws.py`:
      - Potentially new `ErrorCode` enum values for solo-specific errors (e.g., `INVALID_ACTION_IN_SOLO_MODE`, `PLANE_DATA_INCOMPLETE_FOR_GUESS`).
    - `backend/schemas/room.py`: Review `RoomMeta` and `RoomState` to ensure they gracefully handle solo room specifics (e.g., `host_nickname` is the solo player, `round_timeout_seconds` is irrelevant).

2.  **Router Logic (`backend/routes/rooms.py`)**:

    - **REST Endpoint `POST /api/v0/rooms/{code}/join`**:
      - Modify to handle `code == "solo"` by creating a unique, isolated solo game instance.
    - **WebSocket Handler `/ws/{room_code}/{nickname}`**:
      - Add logic branch to handle WebSocket connections and messages for solo rooms differently from multiplayer rooms.
      - Implement handlers for `selectPlane`, `guess`, and `leave` specific to solo mode.
      - Ensure host-only commands are appropriately handled (ignored or error) in solo mode.

3.  **Service Logic (`backend/services/`)**:

    - **`backend/services/room_service.py`**:
      - New function: `async def create_solo_room_instance(nickname: str, redis_client: RedisClient) -> Tuple[str, RoomMeta]`: To generate a unique room ID, create, and store `RoomMeta` for a solo game.
      - Adapt `set_round_data` and `get_round_data` (or create new variants like `set_solo_player_selection_context`, `get_solo_player_selection_context`) to manage the solo player's currently selected plane and guess direction using a simplified structure in Redis.
    - **`backend/services/scoring_service.py`**: Existing scoring functions are expected to be reusable.

4.  **Unit Tests (`tests/backend/`)**:

    - `tests/backend/services/test_room_service.py`: Test `create_solo_room_instance` and solo player context management.
    - `tests/backend/routes/test_rooms_api.py`: Test `POST /api/v0/rooms/solo/join`.
    - `tests/backend/routes/test_rooms_ws.py`: Test WebSocket message handling for solo mode (mocking services where appropriate), including `selectPlane`, `guess`, `leave`, and error conditions.

5.  **Integration Tests (`tests/integration/test_solo_mode.py` - new file)**:

    - End-to-end test flow for solo mode: join, connect WebSocket, select plane, receive confirmation, guess, receive result, leave.
    - Test error handling (e.g., selecting a plane with insufficient data, attempting host actions).
    - Test multiple concurrent solo sessions do not interfere.

6.  **OpenAPI & WebSocket Schemas (`docs/`)**:

    - **`docs/api_openapi.yaml`**: Update description of `POST /api/v0/rooms/{code}/join` to mention special handling for `code="solo"`. Run `make openapi` and commit changes.
    - **`docs/ws_schema.yaml`**:
      - Update descriptions for `selectPlane`, `planeSelectedConfirm`, and `roundResult` messages to include their usage in solo mode.
      - Add new `ErrorCode` values if implemented (e.g., `INVALID_ACTION_IN_SOLO_MODE`, `PLANE_DATA_INCOMPLETE_FOR_GUESS`).
      - Increment schema version if changes are significant.

7.  **Documentation (`README.md`, `backend/README.md`, `docs/PRD.md`)**:
    - Update `README.md` and `backend/README.md` with instructions on how to use/test solo mode.
    - Optionally, add an addendum to `docs/PRD.md` if implementation details significantly clarify the original solo mode description.

### Steps / Detailed Implementation Plan

#### 1. REST API Endpoint Modification (`POST /api/v0/rooms/{code}/join`)

- **File**: `backend/routes/rooms.py`, endpoint function `join_room_api_v0_rooms__room_code__join_post`.
- **Logic**:
  1.  Check if `room_code == "solo"`.
  2.  If `True`:
      - Call a new service function, e.g., `room_service.create_solo_room_instance(nickname=join_request.nickname, redis_client=redis)`.
      - This service function will:
        - Generate a unique `internal_solo_room_id` (e.g., `f"solo:{uuid.uuid4().hex[:8]}"`).
        - Create `RoomMeta` with:
          - `code = internal_solo_room_id`
          - `host_nickname = join_request.nickname`
          - `mode = ScoringMode.Exact` (or `Distance`, make a default choice, e.g., Exact)
          - `round_timeout_seconds = 0` (or a very large number, as it's not used)
          - `created_ts = time.time()`
          - `is_solo = True` (Consider adding this field to `RoomMeta` for clarity).
        - Store this `RoomMeta` in Redis under `room:{internal_solo_room_id}:meta`.
        - Return the `internal_solo_room_id` and the created `RoomMeta`.
      - The endpoint then proceeds to add the player to this `internal_solo_room_id` using existing or adapted `room_service.add_player` logic.
      - Construct `ws_url` using the `internal_solo_room_id` and `join_request.nickname`.
      - Return `RoomJoinResponse` with the WebSocket URL.
  3.  If `False` (not "solo"):
      - Maintain existing logic for joining multiplayer rooms.

#### 2. WebSocket Handler Modifications (`/ws/{room_code}/{nickname}`)

- **File**: `backend/routes/rooms.py`, function `websocket_endpoint`.
- **Connection Logic**:
  1.  On connection, check if `room_code.startswith("solo:")`. This identifies a solo room.
  2.  Set a flag `is_solo_mode = True` for the connection handler's scope.
  3.  `ConnectionManager` will manage the connection as usual.
  4.  Send `stateSync`: Payload should reflect a simple room with one player (the solo player). `RoomState` should be populated based on the solo room's meta and player data.
- **Message Handling (if `is_solo_mode == True`)**:

  - **`selectPlane {hex}` (Client → Server)**:

    1.  Receive `SelectPlanePayload`.
    2.  Fetch `PlaneState` from Redis for `payload.hex` (e.g., `plane:{payload.hex}`).
    3.  If `PlaneState` not found, send `ErrorPayload(code=ErrorCode.PLANE_NOT_FOUND, message="Selected plane data not available.")`.
    4.  Determine `guess_direction` and `correct_airport_code`:
        - Let `origin = plane_state.origin` and `destination = plane_state.destination`.
        - If `origin` AND `destination`: Randomly choose `guess_direction` ("origin" or "destination").
        - Else if `origin` (and not `destination`): `guess_direction = "origin"`.
        - Else if `destination` (and not `origin`): `guess_direction = "destination"`.
        - Else (neither known or both are empty/null): Send `ErrorPayload(code=ErrorCode.PLANE_DATA_INCOMPLETE_FOR_GUESS, message="Selected plane has insufficient route data for guessing.")` and stop.
        - `correct_airport_code` is set based on `guess_direction`.
    5.  Store context:
        - Use an adapted `RoundData`-like structure (let's call the Redis key `room:{room_code}:solo_context`).
        - Store: `selected_plane_hex = payload.hex`, `determined_guess_direction`, `determined_correct_airport_code`.
        - Example function: `await room_service.set_solo_player_selection_context(room_code, selection_data, redis_client)`.
    6.  Send `PlaneSelectedConfirmPayload` to client:
        - `hex = payload.hex`
        - `origin = plane_state.origin`
        - `destination = plane_state.destination`
        - `guess_direction = determined_guess_direction`

  - **`guess {airport_code}` (Client → Server)**:

    1.  Receive `GuessPayload`.
    2.  Retrieve solo player's selection context from Redis (e.g., `room:{room_code}:solo_context`).
    3.  If no `selected_plane_hex` in context (player hasn't selected a plane or guessed already), send `ErrorPayload(code=ErrorCode.INVALID_STATE_FOR_ACTION, message="Please select a plane first.")`.
    4.  Use `scoring_service.calculate_score` (passing the player's guess, the `correct_airport_code` from context, and the scoring mode from `RoomMeta`).
    5.  Update player's total score in `room:{room_code}:players`.
    6.  Prepare `RoundResultPayload`:
        - `results`: List with a single `RoundResultDetail` for the solo player (nickname, guess, correct_code, score_awarded, new_total_score).
        - `next_host_nickname`: `null`.
    7.  Send `WSMessage(type="roundResult", payload=...)` to the client.
    8.  Clear the selection context from Redis (e.g., remove `room:{room_code}:solo_context` or clear its fields) so the player can select a new plane.

  - **Host-Specific Commands (e.g., `startRound`, `skipRound`, `transferHost`)**:

    - If received, send `ErrorPayload(code=ErrorCode.INVALID_ACTION_IN_SOLO_MODE, message="This action is not available in solo mode.")`.

  - **`leave {}` (Client → Server)**:
    - Perform cleanup:
      - `conn_manager.disconnect(websocket, room_code)`.
      - Delete Redis keys for the solo room: `room:{room_code}:meta`, `room:{room_code}:players`, `room:{room_code}:solo_context` (if it exists).
      - Example function: `await room_service.delete_room_data(room_code, redis_client)`.

- **Message Handling (if `is_solo_mode == False`)**: Maintain existing multiplayer logic.

#### 3. Service Layer (`backend/services/room_service.py`)

- **`async def create_solo_room_instance(nickname: str, redis_client: RedisClient) -> Tuple[str, RoomMeta]`**:

  1.  `internal_solo_room_id = f"solo:{uuid.uuid4().hex[:12]}"` (using a slightly longer UUID portion for better uniqueness).
  2.  `current_ts = time.time()`.
  3.  `room_meta = RoomMeta(`
      - `code=internal_solo_room_id,`
      - `host_nickname=nickname,`
      - `mode=ScoringMode.Exact,` # Default scoring mode
      - `round_timeout_seconds=0,`
      - `created_ts=current_ts,`
      - `host_disconnected_ts=None,`
      - `is_solo=True` # Add this field to RoomMeta Pydantic model
        `)`
  4.  `await redis_client.set_model(f"room:{internal_solo_room_id}:meta", room_meta)`
  5.  Return `internal_solo_room_id, room_meta`.

- **Player Management**: `add_player`, `get_player`, `update_player_score`, `remove_player` should generally work if they correctly use the passed `room_code` (which will be the `internal_solo_room_id`). `get_all_players` will return a list with one player.

- **Solo Context Management**:

  - Define a simple Pydantic model for solo context, e.g., `SoloSelectionContext(BaseModel)`:
    - `selected_plane_hex: Optional[str] = None`
    - `correct_airport_code: Optional[str] = None`
    - `guess_direction: Optional[str] = None`
  - `async def set_solo_player_selection_context(room_code: str, context: SoloSelectionContext, redis_client: RedisClient)`:
    - `await redis_client.set_model(f"room:{room_code}:solo_context", context)`
  - `async def get_solo_player_selection_context(room_code: str, redis_client: RedisClient) -> Optional[SoloSelectionContext]`:
    - `return await redis_client.get_model(f"room:{room_code}:solo_context", SoloSelectionContext)`
  - `async def clear_solo_player_selection_context(room_code: str, redis_client: RedisClient)`:
    - `await redis_client.delete(f"room:{room_code}:solo_context")`

- **`async def delete_room_data(room_code: str, redis_client: RedisClient)`**:
  - Adapt to delete `solo_context` key as well if it's a solo room.
  - `keys_to_delete = [f"room:{room_code}:meta", f"room:{room_code}:players", f"room:{room_code}:round", f"room:{room_code}:solo_context"]`
  - `await redis_client.delete(*keys_to_delete)`

#### 4. Redis Schema Updates

- **New/Modified Keys for Solo Rooms**:
  - `room:solo:<UUID>:meta` (HASH, stores `RoomMeta`)
  - `room:solo:<UUID>:players` (HASH, stores `{nickname: Player}`)
  - `room:solo:<UUID>:solo_context` (JSON String, stores `SoloSelectionContext`)
  - The `room:{code}:round` key will NOT be used for solo mode.

#### 5. Error Codes (`backend/schemas/ws.py - ErrorCode Enum`)

- Add if necessary:
  - `PLANE_DATA_INCOMPLETE_FOR_GUESS = "PLANE_DATA_INCOMPLETE_FOR_GUESS"`
  - `INVALID_ACTION_IN_SOLO_MODE = "INVALID_ACTION_IN_SOLO_MODE"`

### Important Context & Assumptions

- The flight data ingest process (`backend/ingest/`) correctly populates `origin` and `destination` fields in the `PlaneState` objects in Redis. The solo mode relies on this data being available for guessing.
- Existing `RedisClient` utility functions (`set_model`, `get_model`, `delete`) will be used.
- The frontend will handle the "solo" room code initiation (e.g., a button that triggers `POST /api/v0/rooms/solo/join`).
- Client-side logic for `selectPlane` and submitting `guess` will need to be implemented in the frontend.

### Open Questions during Implementation

- **Default Scoring Mode for Solo**: Currently set to `Exact`. Confirm if this is desired or if `Distance` should be the default, or if it should be configurable (though PRD implies less config for solo).
- **`is_solo` field in `RoomMeta`**: Adding this boolean flag to `RoomMeta` is proposed for explicit state checking. Confirm this approach.
- **Behavior if AeroAPI/OpenSky enrichment fails**: If `origin`/`destination` are consistently missing for many planes, the solo mode experience might be poor. This is more of an ingest/enrichment robustness concern but impacts solo mode.

<!-- End of Solo Mode Feature Specification -->

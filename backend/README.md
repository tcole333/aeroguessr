# Backend

This directory contains the Python backend service for the Plane Guessing Game, built with FastAPI.

## Overview

The backend is responsible for:

- Ingesting and parsing live ADS-B flight data.
- Enriching flight data with details like callsign, origin country (from OpenSky) and origin/destination airports (from FlightAware AeroAPI), caching the results.
- Smoothing flight position data using a Kalman filter.
- Managing game rooms and player state using Redis.
- Handling real-time communication with clients via WebSockets.
- Providing a REST API for room management and other actions.

## Key Components

### Ingest (`backend/ingest/`)

Handles the connection to the ADS-B data source (e.g., `dump1090`), parsing, enrichment, smoothing, and storage.

**`parser.py`**:

- Contains the `parse_sbs_message` function, which takes raw SBS-1 formatted strings (typically from TCP port 30003) and attempts to parse them into a structured `RawMessage` object.
- **Input:** A single line string in SBS-1 format and a reception timestamp.
- **Output:** A `RawMessage` dataclass instance containing extracted fields (like `hex_ident`, `msg_type`, `altitude`, `latitude`, `longitude`, `callsign`, etc.) if the input is a valid `MSG` type message, otherwise `None`.
- **Usage Example:**

  ```python
  import time
  from backend.ingest.parser import parse_sbs_message

  sbs_line = "MSG,3,1,1,AC1234,1,2023/01/01,12:00:00.000,2023/01/01,12:00:00.000,,35000,,,47.123,-1.456,,,,"
  timestamp = time.time()
  raw_message = parse_sbs_message(sbs_line, timestamp)

  if raw_message:
      print(f"Parsed Plane {raw_message.hex_ident}: Alt={raw_message.altitude}, Lat={raw_message.latitude}, Lon={raw_message.longitude}")
  ```

**`enrichment.py`**:

- Provides `fetch_opensky_data` to get supplementary data (callsign, origin country, category) for a given ICAO24 hex ID from the OpenSky Network API.
- Provides `fetch_aeroapi_route` to get origin and destination airport ICAO codes for a given ICAO24 hex ID from the FlightAware AeroAPI (`/flights/{hex_ident}`).
- Requires `httpx` for API calls.
- Requires optional `OPENSKY_USERNAME` and `OPENSKY_PASSWORD` environment variables.
- Requires `FLIGHTAWARE_API_KEY` environment variable for AeroAPI access.
- Caches OpenSky results (`enrich_cache:{hex}`) for 24 hours.
- Caches AeroAPI results (`aeroapi_route:{hex}`) for 6 hours.
- Defines `EnrichedData` and `RouteData` Pydantic models.

**`smoother.py`**:

- Provides the `PositionSmoother` class, which wraps a Kalman filter (`filterpy.kalman.KalmanFilter`) to smooth noisy position data (latitude, longitude, altitude).
- Uses a constant velocity model (6 state dimensions: position + velocity for lat/lon/alt).
- Requires initial position measurement and configurable process/measurement noise parameters.
- **Input:** Initial position (`np.ndarray`), process noise variance (`float`), measurement noise variance (`float`). Subsequently takes time delta (`dt: float`) for `predict` and new position measurements (`np.ndarray`) for `update`.
- **Output:** Access smoothed state via properties like `position`, `velocity`, `state`.
- **Usage Example:**

  ```python
  import numpy as np
  from backend.ingest.smoother import PositionSmoother

  # Example initial measurement and noise
  initial_measurement = np.array([42.123, -71.456, 30000.0])
  process_noise_variance = 0.5  # How much velocity might change
  measurement_noise_variance = 10.0 # How noisy the sensor reading is

  smoother = PositionSmoother(
      initial_pos=initial_measurement,
      process_noise=process_noise_variance,
      measurement_noise=measurement_noise_variance
  )

  # Later, when a new message arrives...
  dt = 1.5 # Time since last update in seconds
  new_measurement = np.array([42.124, -71.458, 29950.0])

  smoother.predict(dt)
  smoother.update(new_measurement)

  smoothed_position = smoother.position
  smoothed_velocity = smoother.velocity
  print(f"Smoothed Pos: {smoothed_position}, Smoothed Vel: {smoothed_velocity}")
  ```

**`main.py`**:

- Contains the main asynchronous ingest loop (`run_ingest_loop`) and message handler (`handle_message`).
- Connects to the configured ADS-B TCP source (`ADSB_HOST`, `ADSB_PORT`).
- Reads incoming SBS-1 messages line by line.
- Uses `parser.parse_sbs_message` to decode valid messages.
- For new aircraft, calls `enrichment.fetch_opensky_data` and `enrichment.fetch_aeroapi_route` to get and cache supplementary data.
- Manages `PositionSmoother` instances in memory for each active aircraft hex ID.
- Calculates time deltas (`dt`) between position updates for each aircraft.
- Calls `smoother.predict(dt)` and `smoother.update(measurement)`.
- Retrieves existing state from Redis, appends the new smoothed position to a trail (capped at 30 points).
- Stores the resulting smoothed `PlaneState` (a Pydantic model including position, velocity, trail, callsign, country, category, origin, and destination) in Redis using `RedisClient.set_json`, applying a TTL (`PLANE_TTL_SECONDS`).
- Handles connection errors and attempts reconnections.
- Can be run directly (`python -m backend.ingest.main`) using environment variables for configuration.

### Schemas (`backend/schemas/`)

Contains Pydantic models used for data validation, serialization, and defining the structure of data used within the API and potentially stored in Redis.

**`core.py`**: Defines fundamental models like `Player`, `RoomMeta`, and `ScoringMode`.
**`room.py`**: Defines schemas specific to room creation and management, such as `RoomCreateRequest`, `RoomCreateResponse`, `RoomJoinRequest`, and `RoomJoinResponse`.
**`game.py`**: Defines schemas for game state, including `RoundStateEnum`, `RoundData`, `PlayerGuess`, and `RoundResultDetail`.
**`ws.py`**: Defines the wrapper `WSMessage` model and specific payload schemas for each WebSocket message type (e.g., `PingPongPayload`, `GuessPayload`, `RoundStartPayload`, `RoundResultPayload`, `ErrorPayload`).

### Routes (`backend/routes/`)

Contains FastAPI `APIRouter` instances, grouping related API endpoints.

**`rooms.py`**: Handles REST endpoints and the primary WebSocket connection for game rooms.

- REST Endpoints:
  - `POST /api/v0/rooms`: Creates a new game room.
  - `POST /api/v0/rooms/{code}/join`: Allows a player to join an existing room.
  - `POST /api/v0/rooms/solo/join`: Start a single-player session with its own room code.
- WebSocket Endpoint (`/ws/{room_code}/{nickname}`):
  - Manages player connections using `ConnectionManager`.
  - Handles incoming messages (`ping`, `guess`, `selectPlane`, `startRound`, `transferHost`, `claimHost`, `leave`).
  - Implements the core game logic, including round state transitions (`WAITING_FOR_SELECTION` -> `ACCEPTING_GUESSES` -> `SHOWING_RESULTS`).
  - Uses `room_service` and `scoring` service modules for managing state and calculating scores.
  - Handles round timing via `asyncio` tasks.
  - Implements host disconnect/transfer logic (2-min claim window, 5-min auto-transfer).
  - Broadcasts game state updates and events (`stateSync`, `delta`, `roundStart`, `roundResult`, `playerJoined`, `playerLeft`, `newHost`) to clients.

### Services (`backend/services/`)

Holds the core business logic, separated from the API routing layer.

**`room_service.py`**:

- Provides functions to interact with Redis for managing room and player state.
- Includes helpers for getting/setting `RoomMeta`, `Player` data (within `room:{code}:players` HASH), and `RoundData`.
- Functions like `get_player`, `add_player`, `update_player_status`, `update_player_score`, `get_all_players`, `remove_player`, `get_room_meta`, `set_room_meta`, `get_round_data`, `set_round_data`.

**`scoring.py`**:

- Contains functions for calculating player scores based on game mode.
- Implements `calculate_exact_score` and `calculate_distance_score` (with placeholder distance calculation).

### Utils (`backend/utils/`)

Contains helper functions and classes used across the backend.

**`redis_async.py`**: Provides the `RedisClient` class, a wrapper around `redis-py`'s async capabilities for common operations like:

- Connecting to Redis using a connection pool.
- Setting/getting JSON serialized Pydantic models (`set_json`, `get_model`).
- Setting/getting JSON serialized Pydantic models within Redis Hashes (`hset_model`, `hget_model`, `hgetall_models`).
- Deleting fields from Hashes (`hdel`).
- Setting key expiry (`expire`).
- Checking key existence (`exists`).

## Testing (`tests/backend/`)

The backend uses `pytest` for testing. Tests are categorized into:

- **Unit Tests:** Test individual functions or classes in isolation, often using mocks or `fakeredis` (if Redis interaction is simple and can be faked). These can be run directly via `poetry run pytest tests/backend`. Filenames typically follow `test_*.py`.
- **Integration Tests:** Test the interaction between different components, particularly those involving external services like Redis. These tests require a running Redis instance (provided by `infra/docker-compose.test.yml`) and are marked with `@pytest.mark.integration`. Filenames typically follow `test_*_integration.py`.

To run **unit tests** locally:

```bash
poetry run pytest tests/backend -m "not integration"
```

To run **integration tests** (requires Docker):

1. Ensure Docker is running.
2. Use the Makefile target:
   ```bash
   make integration-test
   ```
   This command:
   - Builds the necessary Docker images (`infra/Dockerfile.test`).
   - Starts a dedicated Redis container (`redis-test`).
   - Starts the backend container connected to `redis-test`.
   - Executes `pytest -m integration` inside the backend container.
   - Stops and removes the containers afterwards.

To run **all** backend tests locally (unit tests using `fakeredis` where possible, integration tests will likely fail without the Docker setup):

```bash
poetry run pytest tests/backend
```

## Running Locally

1.  Ensure you have Python 3.12+ and Poetry installed.
2.  Create a `.env` file in the project root directory (copy `.env.example` and fill in values like `REDIS_URL`, `FLIGHTAWARE_API_KEY`, etc.).
3.  Navigate to the project root directory in your terminal.
4.  Install dependencies: `poetry install`
5.  Start the FastAPI development server:

    ```bash
    poetry run uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
    ```

6.  Access the API docs at `http://localhost:8000/docs`.
7.  To run the ingest service (requires a running Redis instance and ADS-B source configured in `.env`):

    ```bash
    poetry run python -m backend.ingest.main
    ```

_(Further sections on Services, Testing will be expanded)_

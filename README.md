# Plane Guessing Game

<!-- Add badges here: e.g., Build Status, Coverage, License -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/your-username/plane-game-v4/actions/workflows/test.yml/badge.svg)](https://github.com/your-username/plane-game-v4/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/your-username/plane-game-v4/branch/main/graph/badge.svg)](https://codecov.io/gh/your-username/plane-game-v4)

<!-- ![Build Status](...) -->
<!-- ![Code Coverage](...) -->

## 1. Purpose

A casual, real-time web game where players guess the origin or destination of flights overhead using live ADS-B signals. Players join a shared "room" via a code, competing in timed rounds. See the full [Product Requirements Document](docs/PRD.md).

## 2. TL;DR Usage

```bash
# Ensure Docker and Docker Compose are installed
# Create a .env file from .env.example and fill in values (e.g., OpenSky credentials)
cp .env.example .env
# ... edit .env ...

# Start the application stack
docker compose up --build -d

# Access the frontend at http://localhost (or your Pi's IP)
# Access the backend API docs at http://localhost:8000/docs (or your Pi's IP:PORT)
```

_(Note: Port mapping might vary based on `docker-compose.yml` configuration)_

## 3. Context for LLMs

- **Core Functionality:** Real-time flight tracking map game, room-based multiplayer, flight data ingestion from ADS-B.
- **Backend:** Python 3.12, FastAPI, Redis (cache/state), Pydantic, SQLAlchemy (potentially later). Handles ADS-B ingest, game logic, WebSocket communication. (`backend/`)
- **Frontend:** React 18, TypeScript, Vite, Zustand (state), Tailwind CSS, Leaflet (map). Displays map, game state, handles user input. (`frontend/`)
- **Infra:** Docker Compose for local dev/deployment, Nginx for serving frontend static files. (`infra/`)
- **Data:** Live ADS-B via `dump1090`, enriched with OpenSky API data. Sample data available in `sample_data/`.
- **Key Docs:** [PRD](docs/PRD.md), [Standards](docs/project-standards.md), [API Schema](docs/api_openapi.yaml), [WS Schema](docs/ws_schema.yaml).

## 4. Modules

| Folder         | Responsibility                                    | Key Technologies       |
| -------------- | ------------------------------------------------- | ---------------------- |
| `backend/`     | API, WebSocket gateway, game logic, ADS-B ingest  | FastAPI, Redis, Python |
| `frontend/`    | Web user interface, map display, game interaction | React, TS, Leaflet, WS |
| `infra/`       | Docker setup, deployment scripts, Nginx config    | Docker, Nginx, Bash    |
| `docs/`        | Project documentation, standards, schemas, ADRs   | Markdown, YAML         |
| `sample_data/` | Sample ADS-B and airport data for testing         | SBS, JSON              |

## 5. Endpoints / Messages

- **REST API:** Defined in [`docs/api_openapi.yaml`](docs/api_openapi.yaml) (Auto-generated via `make openapi`).
  - `GET /healthz`: Basic health check.
  - `POST /api/v0/rooms`: Creates a new game room.
  - `POST /api/v0/rooms/{code}/join`: Allows a player to join an existing room.
  - `POST /api/v0/rooms/solo/join`: Creates a personal solo room and returns the connection URL.
- **WebSocket Messages:** Defined in [`docs/ws_schema.yaml`](docs/ws_schema.yaml).

_(Example usage snippets will be added as endpoints/messages are implemented)_

## 6. Common Tasks

### 6.1 Running Unit Tests

```python
poetry run tests/
```

### 6.2 Running Integration Tests

#### Using the Makefile (Recommended)

```bash
make integration-test
```

This command will:

1. Build and start the necessary test services (backend + Redis)
2. Run integration tests (marked with `@pytest.mark.integration`)
3. Tear down the test services automatically

#### Manual Approach

If you need more control, you can run the steps individually:

1. Start the test services (backend + Redis):

   ```bash
   docker compose -f infra/docker-compose.test.yml up -d
   ```

2. Run integration tests (marked with `@pytest.mark.integration`):

   ```bash
   docker compose -f infra/docker-compose.test.yml exec backend-test bash -c "cd /app && PYTHONPATH=/app poetry run pytest -q -m integration"
   ```

3. Tear down the test services:

   ```bash
   docker compose -f infra/docker-compose.test.yml down
   ```

Ensure Docker and `docker-compose` are installed.

### 6.3 Replaying Sample ADS-B Data (Offline Mode)

```bash
# Ensure FAKE_ADSB flag is enabled so backend spawns the generator
export FAKE_ADSB=1
# Optional: choose a different capture and/or speed
export FAKE_ADSB_FILE=sample_data/sbs_parser_fixtures.sbs
export FAKE_ADSB_SPEED=5  # 5× faster than real-time

# Run the generator in a separate shell (loops until Ctrl-C)
make sample-replay

# Start the backend as usual (it will connect to localhost:30003)
poetry run uvicorn backend.app:app --reload
```

When `FAKE_ADSB=1`, `backend.ingest.main` automatically spins up the sample
feed even if you don't call `make sample-replay`. The Make target is provided
for quick manual testing or if you want the generator to run independently.

### 6.4 Testing Details

#### 6.4.1 Unit Tests

- **Location:** `tests/backend/`
- **Fixtures:** Defined in `tests/backend/conftest.py`:
  - `fake_redis_instance`: Provides a fresh in-memory FakeRedis for each test.
  - `redis_client`: Overrides the Redis dependency, flushes data, and injects into the app.
  - `test_client`: Async HTTP/WebSocket client against the FastAPI `app`.
- **Run locally:**

```bash
poetry run pytest tests/backend
```

- **CI behavior:** Runs non-integration tests with coverage, matching the GitHub Actions command:

```bash
poetry run pytest --cov=backend \
  --cov-report=xml --cov-report=term-missing \
  -m "not integration" tests/
```

#### 6.4.2 Integration Tests

- **Location:** `tests/integration/`
- **Marker:** Decorated with `@pytest.mark.integration` in test files.
- **Requirements:** Docker & Docker Compose
- **Recommended (Makefile):**

```bash
make integration-test
```

- **Manual steps:**
  1. Start services:
     ```bash
     docker compose -f infra/docker-compose.test.yml up -d

````
  2. Run integration tests:
     ```bash
docker compose -f infra/docker-compose.test.yml exec \
  backend-test bash -c "cd /app && \
  PYTHONPATH=/app poetry run pytest -q -m integration"
````

3. Tear down services:
   ```bash
   docker compose -f infra/docker-compose.test.yml down

````

#### 6.4.3 CI Pipeline
- **Definition:** `.github/workflows/test.yml`
- **Triggers:** Push/PR to `main`, manual dispatch
- **Key steps:**
  1. Starts a Redis service container for tests
  2. Installs dependencies via Poetry
  3. Runs unit tests (non-integration) with coverage reports
  4. Uploads coverage to Codecov
  5. Enforces minimum coverage threshold (50%)
- **Badges:**
```markdown
[![Tests](https://github.com/your-username/plane-game-v4/actions/workflows/test.yml/badge.svg)]
(https://github.com/your-username/plane-game-v4/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/your-username/plane-game-v4/branch/main/graph/badge.svg)]
````

### 6.5 Generating Airport Data

The game uses airport coordinate data for distance scoring. The script generates two datasets:

1. **Backend dataset** (`sample_data/airports_min.json`): ~500K airports for comprehensive coverage
2. **Frontend dataset** (`frontend/src/assets/airports.json`): ~3K major airports for autocomplete (160KB gzipped)

To regenerate airport data:

```bash
python backend/scripts/populate_airports_data.py
```

This downloads the latest OurAirports database and creates both files. The frontend dataset includes only airports with:
- IATA codes (e.g., BOS, JFK, LAX)
- Scheduled commercial service OR large airport classification
- Additional metadata: name, city, country

### 6.6 Logging

- **Log Directory:** All application logs are stored in the `logs/` directory
- **Frontend Logs:** Browser console logs are automatically captured to `logs/frontend.log`
- **Integration Test Logs:** Test output saved to `logs/integration.log` for debugging failures
- **Log Rotation:** Logs are automatically rotated to prevent disk space issues (configured via logrotate)

## 7. FAQ & Gotchas

- **Map Tiles:** Uses OpenStreetMap by default. Be mindful of their [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/). Caching is implemented, but high volume may require switching providers (see [PRD §8.1](docs/PRD.md#81-map-tiles)).
- **OpenSky API:** Requires credentials (`OPENSKY_USERNAME`, `OPENSKY_PASSWORD` in `.env`) for flight data enrichment. Free accounts have rate limits.
- _(More to be added as development progresses)_

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

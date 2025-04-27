# Plane Guessing Game

<!-- Add badges here: e.g., Build Status, Coverage, License -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

## 7. FAQ & Gotchas

- **Map Tiles:** Uses OpenStreetMap by default. Be mindful of their [Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/). Caching is implemented, but high volume may require switching providers (see [PRD §8.1](docs/PRD.md#81-map-tiles)).
- **OpenSky API:** Requires credentials (`OPENSKY_USERNAME`, `OPENSKY_PASSWORD` in `.env`) for flight data enrichment. Free accounts have rate limits.
- _(More to be added as development progresses)_

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

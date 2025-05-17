# Developer Guide: Plane Game v4

This guide provides essential information for developers, including AI agents, to autonomously interact with, develop, test, and contribute to the Plane Game v4 codebase.

## 1. Project Overview

Plane Game v4 is a real-time flight tracking map game with room-based multiplayer.

- **Backend:** Python (FastAPI), Redis, Pydantic (`backend/`)
- **Frontend:** React, TypeScript, Vite, Zustand, Tailwind CSS, Leaflet (`frontend/`)
- **Infrastructure:** Docker Compose, Nginx (`infra/`)
- **Key Documentation:**
  - [Product Requirements (PRD)](./PRD.md)
  - [Project Standards](./project-standards.md)
  - [API Specification (OpenAPI)](./api_openapi.yaml) (Auto-generated)
  - [WebSocket Schema](./ws_schema.yaml) (Auto-generated)
  - [Architecture Decision Records (ADRs)](../ADR/)
  - [Tech Debt Log](../TECH_DEBT.md)

## 2. Initial Setup

1.  **Prerequisites:**

    - Git
    - Python 3.12+
    - Poetry (Python dependency manager)
    - Docker & Docker Compose
    - Node.js & npm/yarn (for frontend development, if applicable)

2.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd plane-game-v4
    ```

3.  **Set up environment variables:**
    Copy the example environment file and populate it with necessary values (e.g., API keys, configurations).

    ```bash
    cp .env.example .env
    # Edit .env with your specific configurations
    ```

4.  **Install backend dependencies:**
    Uses Poetry for dependency management.
    ```bash
    poetry install --with dev
    ```
    This installs both main and development dependencies. The virtual environment will be created inside the project directory (`.venv/`) due to Poetry configuration.

## 3. Running the Application (Local Development)

The application is designed to run with Docker Compose for a consistent environment.

```bash
# Build and start all services (backend, frontend, redis, etc.)
docker compose up --build -d
```

- Frontend will be accessible at `http://localhost` (or your configured port).
- Backend API documentation (Swagger UI) at `http://localhost:8000/docs` (or your backend's configured port/path).

## 4. Backend Development

### 4.1 Running the Backend Server (without Docker)

For quicker iteration on backend code, you can run the FastAPI server directly using Uvicorn (ensure dependencies are installed via `poetry install`):

```bash
poetry run uvicorn backend.app:app --reload --port 8000
```

### 4.2 Generating API and WebSocket Schemas

If you make changes to API routes/schemas (Pydantic models) or WebSocket message structures:

- **Generate OpenAPI spec:**

  ```bash
  make openapi
  ```

  This updates `docs/api_openapi.yaml`. Commit this file with your changes.

- **Generate WebSocket schema:**
  ```bash
  make ws-schema
  ```
  This updates `docs/ws_schema.yaml`. Commit this file with your changes.

## 5. Testing

The project uses `pytest`. Tests are categorized into unit and integration tests.

### 5.1 Unit Tests

- **Location:** `tests/backend/` and potentially `tests/frontend/` in the future.
- **Fixtures:** Backend fixtures are in `tests/backend/conftest.py`.
- **Running all unit tests (backend):**
  ```bash
  poetry run pytest tests/backend -m "not integration"
  ```
- **Running unit tests with coverage (as in CI):**
  ```bash
  poetry run pytest --cov=backend --cov-report=xml --cov-report=term-missing -m "not integration" tests/
  ```

### 5.2 Integration Tests

Integration tests require Docker services (backend, Redis) to be running.

- **Location:** `tests/integration/`
- **Marker:** `@pytest.mark.integration`
- **Running integration tests (Recommended):**
  The `Makefile` provides a convenient target:

  ```bash
  make integration-test
  ```

  This command handles:

  1.  Building and starting test Docker containers (`backend-test`, `redis-test`) using `infra/docker-compose.test.yml`.
  2.  Waiting for the backend to be healthy.
  3.  Executing tests marked with `integration`.
  4.  Collecting container logs to `logs.txt`.
  5.  Tearing down the test containers.
  6.  Exiting with the pytest status code.

- **Manual Integration Test Execution:**
  Refer to the "Manual Approach" section in `README.md` if finer control is needed.

### 5.3 Pytest Configuration

Configuration for pytest can be found in `pytest.ini`. It defines markers like `integration` and `asyncio`.

## 6. Linting and Formatting

The project uses `Ruff` for Python linting and formatting. Pre-commit hooks are configured in `.pre-commit-config.yaml` to enforce standards.

- **Run linters/formatters locally (via pre-commit):**
  ```bash
  pre-commit install # Run once to install the git hooks
  pre-commit run --all-files
  ```
- **Run Ruff directly:**
  ```bash
  ruff check .
  ruff format . # To format
  ruff format --check . # To check formatting
  ```

## 7. CI/CD Pipeline (GitHub Actions)

Workflows are defined in `.github/workflows/`.

### 7.1 `test.yml` (Test & Coverage)

- **Triggers:** Push/PR to `main`, manual dispatch.
- **Jobs:**
  - `test`:
    - Sets up Python, installs Poetry, and caches dependencies.
    - Starts a Redis service.
    - Runs unit tests (those not marked `integration`) with coverage for the `backend` module.
    - Uploads coverage report (`coverage.xml`) to Codecov.
    - Enforces a minimum coverage threshold (e.g., 50%). If below, the check fails.

### 7.2 `lint.yml` (Lint Code)

- **Triggers:** Push/PR to `main`, manual dispatch.
- **Jobs:**
  - `lint`:
    - Sets up Python.
    - Installs and runs `Ruff` for linting (`ruff check .`) and format checking (`ruff format --check .`).
    - Builds the backend Docker image (`backend/Dockerfile`) to catch Dockerfile issues (does not push).
    - (Future: Will include frontend linting with Prettier/ESLint).

**All CI checks must pass for a PR to be mergeable.**

## 8. Dependency Management (Poetry)

- **Tool:** [Poetry](https://python-poetry.org/)
- **Configuration:** `pyproject.toml`
- **Lock file:** `poetry.lock` (Commit this file whenever dependencies change)
- **Adding a new dependency:**
  ```bash
  poetry add <package-name>
  ```
- **Adding a new development-only dependency:**
  ```bash
  poetry add --group dev <package-name>
  ```
- **Updating dependencies:**
  ```bash
  poetry update
  ```
- **Installing dependencies (from `poetry.lock`):**
  ```bash
  poetry install --with dev # For development, including dev dependencies
  poetry install # For production-like, without dev dependencies
  ```

## 9. Using Sample ADS-B Data (Offline Development)

For development or testing without live ADS-B data, you can use the sample data generator.

1.  **Set environment variables:**
    ```bash
    export FAKE_ADSB=1
    # Optional: Specify file and speed
    # export FAKE_ADSB_FILE=sample_data/another_fixture.sbs
    # export FAKE_ADSB_SPEED=2.0 # 2x speed
    ```
2.  **Run the generator (e.g., in a separate terminal):**
    ```bash
    make sample-replay
    ```
    This runs `sample_data/adsb_generator.py`.
3.  Start the backend as usual (e.g., `poetry run uvicorn backend.app:app --reload`). It will attempt to connect to the generator on `localhost:30003` if `FAKE_ADSB=1`.

    _Note: As mentioned in `README.md`, when `FAKE_ADSB=1`, `backend.ingest.main` might automatically try to spawn the sample feed. The `make sample-replay` target is useful for manual control or independent running._

## 10. Committing Changes and Pull Requests

- Follow Conventional Commit message standards (e.g., `feat:`, `fix:`, `docs:`, `refactor:`, `test:`).
- Ensure all tests pass (`make integration-test`, unit tests).
- Ensure linters pass (`pre-commit run --all-files`).
- Update documentation if you change:
  - API behavior (`make openapi` and commit `docs/api_openapi.yaml`).
  - WebSocket schema (`make ws-schema` and commit `docs/ws_schema.yaml`).
  - Major architectural decisions (add an ADR in `ADR/`).
  - Add TODOs/FIXMEs (update `TECH_DEBT.md`).
  - README context (`project_context.mdc` if LLM context section changes).
- Create a Pull Request (PR) targeting the `main` branch.
- Ensure all CI checks pass on the PR.

## 11. Key Project Rules Summary

(Refer to `docs/project-standards.md` and embedded rules in `.cursor/instructions.md` for full details)

- Explain code changes.
- Update tests and documentation with logic changes.
- Modified files must pass `pre-commit` checks.
- `sample_data/` functionality must mirror live ADS-B behavior when `FAKE_ADSB=1`.
- Update `docs/ws_schema.yaml` and PRD for WebSocket payload changes.
- Do not remove existing functionality without instruction.
- Ask for clarification if requirements are unclear.
- Prioritize readability, maintainability, simplicity.
- After API changes, run `make openapi` and include `docs/api_openapi.yaml` in commit.
- Record major architectural decisions in `ADR/`.
- New TODOs/FIXMEs in code need a `TECH_DEBT.md` entry.

This guide should serve as a good starting point. Refer to the specific files and documents linked for more detailed information.

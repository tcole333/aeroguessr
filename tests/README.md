# Testing Strategy & Setup

This document provides a detailed overview of the testing setup for the Plane Guessing Game project, intended for both human developers and LLM analysis.

**Core Principles:**

1.  **Separation:** Unit tests (`tests/backend/`) run in isolation using mocks/fakes, while integration tests (`tests/integration/`) require live Docker services.
2.  **Fixtures:** Pytest fixtures are heavily used for setup, teardown, and dependency injection (DI), defined primarily in `conftest.py` files.
3.  **Markers:** Pytest markers (`@pytest.mark.*`) distinguish test types (e.g., `@pytest.mark.integration`).
4.  **Automation:** Tests are run automatically via GitHub Actions (`.github/workflows/test.yml`) and can be invoked locally using `Makefile` targets or direct `poetry run pytest` commands.

## 1. Test Types & Locations

| Directory            | Test Type       | Purpose                                               | Dependencies                   | Marker                     |
| -------------------- | --------------- | ----------------------------------------------------- | ------------------------------ | -------------------------- |
| `tests/backend/`     | **Unit**        | Test individual functions, classes, and modules       | Mocked/Faked (e.g., FakeRedis) | _(none)_                   |
| `tests/integration/` | **Integration** | Test interactions between services (Backend <> Redis) | Live Docker Services           | `@pytest.mark.integration` |

## 2. Key Fixtures

Fixtures provide reusable setup/teardown logic for tests.

### 2.1 Unit Test Fixtures (`tests/backend/conftest.py`)

These fixtures are function-scoped, meaning they are recreated for each test function, ensuring isolation.

- `fake_redis_instance` -> `fakeredis.aioredis.FakeRedis`:
  - **Purpose:** Provides a fresh, in-memory simulation of an asynchronous Redis instance.
  - **Scope:** `function`
- `redis_client` -> `backend.utils.redis_async.RedisClient`:
  - **Purpose:** Creates a `RedisClient` wrapper around the `fake_redis_instance` for the test. It overrides the application's `get_redis` dependency injector, ensuring the FastAPI app uses the fake Redis during the test. It also flushes the fake Redis before yielding the client.
  - **Scope:** `function`
  - **Dependencies:** `fake_redis_instance`
- `test_client` -> `httpx.AsyncClient`:
  - **Purpose:** Provides an asynchronous HTTP client configured to interact directly with the FastAPI `app` object (using `ASGIWebSocketTransport`). This allows testing API endpoints and WebSocket connections without needing a running server. The FastAPI `app` instance used by this client automatically benefits from the `redis_client` fixture's dependency override.
  - **Scope:** `function`

### 2.2 Integration Test Fixtures (`tests/integration/conftest.py`)

These fixtures connect to _live_ services defined in `infra/docker-compose.test.yml`.

- `integration_client` -> `httpx.AsyncClient`:
  - **Purpose:** Provides an asynchronous HTTP client that connects to the actual `backend-test` service running in Docker Compose. It includes logic to wait for the service's `/healthz` endpoint to return 200 OK before yielding the client, ensuring the backend is ready.
  - **Scope:** `function`
- `integration_redis` -> `redis.asyncio.Redis`:
  - **Purpose:** Provides a standard asynchronous Redis client connected directly to the `redis-test` service running in Docker Compose.
  - **Scope:** `function`

## 3. Running Tests

Refer to **Section 6. Common Tasks** in the main [`README.md`](../README.md) for detailed commands.

- **All Unit Tests (Local):**
  ```bash
  poetry run pytest -m "not integration" tests/
  ```
- **All Integration Tests (Local - Recommended):**
  ```bash
  make integration-test
  ```
- **Specific Tests/Modules:** Use standard pytest selectors (e.g., `poetry run pytest tests/backend/routes/test_rooms.py::test_create_room`).
- **CI Execution:** The `.github/workflows/test.yml` workflow runs **unit tests only** (`-m "not integration"`) with coverage reporting against the Python backend code. Integration tests are typically run manually or in separate CI/CD stages involving deployed environments.

## 4. Configuration

- **`pytest.ini`:** Defines global pytest settings, including ignored paths (`test_logs.py`) and custom markers (`integration`).
- **`pyproject.toml`:** Specifies test dependencies (`pytest`, `pytest-asyncio`, `httpx`, `fakeredis`, etc.) under `[tool.poetry.group.dev.dependencies]`.

## 5. LLM Guidance

- To understand **unit testing setup**, focus on `tests/backend/conftest.py` and how the `redis_client` fixture overrides dependencies for the `test_client`.
- To understand **integration testing setup**, focus on `tests/integration/conftest.py`, `infra/docker-compose.test.yml`, and the `make integration-test` target in the `Makefile`. Note that these tests require external services.
- Test files are organized mirroring the `backend/` source structure (e.g., `backend/routes/rooms.py` is tested by `tests/backend/routes/test_rooms.py`).
- The `integration` marker defined in `pytest.ini` is crucial for separating test suites.

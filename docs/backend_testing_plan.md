# Backend Testing Status & Remediation Plan

## 1. Current Status

- **REST API Tests (`tests/backend/routes/test_rooms.py`):**

  - Utilizes `httpx.AsyncClient` and a `fakeredis` fixture for unit testing.
  - Provides good baseline coverage for the `POST /api/v0/rooms` (create) and `POST /api/v0/rooms/{code}/join` endpoints, including success paths and common errors (404 Not Found, 409 Conflict).
  - **Gaps:** Lacks tests for input validation errors, `DELETE /api/v0/rooms/{code}`, and `GET /api/v0/rooms/{code}` (if implemented).

- **WebSocket Tests (`tests/backend/routes/test_websocket.py`):**

  - **Critically Lacking:** All tests within this module are currently **disabled** via `pytest.skip`.
  - The existing (disabled) test structure uses `httpx_ws` and helper functions, demonstrating intent to cover basic scenarios (connect, ping/pong, join/leave broadcasts, invalid connection attempts).
  - **Gaps (Major):** No active tests verify any WebSocket functionality. Even if enabled, the existing tests lack coverage for the core game loop, host actions, plane data broadcasting (`delta` messages), error handling for invalid messages/states, and host transfer logic.

- **Integration Test Setup (`infra/docker-compose.test.yml`, `Makefile`):**
  - An integration testing environment is configured using Docker Compose to run the backend API and a dedicated Redis instance.
  - The `make integration-test` command correctly orchestrates building, running services, executing tests (marked `@pytest.mark.integration`), and tearing down.
  - This setup was chosen specifically to enable reliable testing of WebSocket interactions against live services, addressing previous challenges. **This setup should be the primary method for running WebSocket tests.**

## 2. Identified Gaps (Focus on WebSocket)

The most significant gaps are in WebSocket testing:

- **Basic Lifecycle:** Connection success (`stateSync` verification), disconnection, ping/pong liveness.
- **Player Events:** `playerJoined` and `playerLeft` broadcast verification.
- **Plane Data:** Verification of `delta` message broadcasts containing `updated` and `removed` plane data originating from the background task.
- **Game Host Actions:** Testing `selectPlane` and `startRound` messages and their effects (state changes, broadcasts).
- **Game Player Actions:** Testing `guess` message submission during active rounds.
- **Round Logic:** Testing round start/end based on timers or all players guessing, and verification of `roundResult` broadcasts.
- **Error Handling:** Testing server responses to invalid messages, actions performed in the wrong state (e.g., guess outside round), and non-host attempting host actions.
- **Host Management:** Testing host disconnect, transfer, and claim logic.

## 3. Remediation Plan

The following steps prioritize enabling and expanding WebSocket tests using the existing integration test (`make integration-test`) framework.

- **Priority 1: Enable & Verify Basic WebSocket Tests**

  1.  Remove `pytest.skip` from `tests/backend/routes/test_websocket.py`.
  2.  Run `make integration-test` and resolve any immediate failures in the previously disabled tests (connect/sync, ping/pong, join/leave broadcasts, invalid room/player rejection).
  3.  Ensure these foundational tests pass reliably in the integration environment.

- **Priority 2: Implement Core Game Loop Tests (Integration)**

  1.  Add new integration tests in `test_websocket.py` covering:
      - Host selects a valid plane (`selectPlane`) -> verify host confirmation message and Redis state. (Requires adding test plane data to Redis).
      - Host starts a round (`startRound`) -> verify `roundStart` broadcast to all clients.
      - Player submits a guess (`guess`) -> verify guess stored in Redis.
      - Round timeout expiry -> verify `roundResult` broadcast.
      - Round end (all players guess) -> verify `roundResult` broadcast.
      - Verify `roundResult` payload structure and basic content (scoring logic can be simplified/mocked initially if needed).

- **Priority 3: Implement Plane Delta Broadcast Test (Integration)**

  1.  Add an integration test where:
      - A client connects and receives initial `stateSync`.
      - The test manually manipulates `plane:<hex>` data in the connected Redis instance (add/update/delete).
      - Verify the client receives `delta` messages reflecting these changes accurately in the `updated` and `removed` fields.

- **Priority 4: Implement Error Handling & Edge Case Tests (Integration)**

  1.  Add tests sending invalid WebSocket message formats or types.
  2.  Add tests for actions in incorrect states (e.g., `guess` when no round is active).
  3.  Add tests for non-hosts attempting host-only actions (`selectPlane`, `startRound`).
  4.  _(Stretch)_ Add tests for host disconnect/transfer/claim scenarios (may require managing multiple client connections simultaneously in the test).

- **Priority 5: Minor REST API Improvements (Unit Tests)**
  1.  Add tests to `test_rooms.py` for input validation errors (e.g., invalid nickname length, invalid scoring mode).
  2.  Add tests for `DELETE` and `GET` `/api/v0/rooms/{code}` endpoints if/when implemented.

## 4. Testing Strategy Notes

- **Primary Workflow:** Use `make integration-test` for running all WebSocket-related tests to ensure they execute against the live API and Redis stack as intended.
- **Fixtures:** Consider enhancing `tests/backend/conftest.py` with fixtures to manage the setup/teardown of rooms and multiple WebSocket client connections for more complex scenarios, reducing test boilerplate.
- **Mocking:** While integration tests use live services, mocking may still be needed for external dependencies (e.g., OpenSky/AeroAPI calls within the ingest service if testing specific enrichment side effects) or to precisely control data for specific test cases (like injecting specific plane data into Redis).

By executing this plan, we can build high confidence in the backend's WebSocket functionality before proceeding with significant frontend development.

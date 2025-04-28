## 🐞 Item: Integration Test Failures (WebSocket 403 & Event Loop Closed)

- **Context:** The `make integration-test` command is failing with two distinct errors in `tests/integration/test_websocket_integration.py` after refactoring tests to use `httpx.AsyncClient` against a running Docker service (`integration_client` fixture):
  1.  `test_websocket_connect_and_state_sync_integration`: Fails with `httpx_ws._exceptions.WebSocketUpgradeError: <Response [403 Forbidden]>`. The WebSocket connection handshake is rejected by the server.
  2.  `test_websocket_player_join_broadcast_integration`: Fails with `RuntimeError: Event loop is closed`. This occurs during the initial HTTP POST request within the test.
- **Checks Performed:**
  - Confirmed tests were refactored to use `httpx.AsyncClient` and `httpx_ws.aconnect_ws`.
  - Corrected tests to request the `integration_client: AsyncClient` fixture instead of the old `http_server: TestClient` fixture.
- **Potential Issues / Next Steps:**
  - **403 Forbidden:**
    - Examine server-side validation logic in `backend/routes/rooms.py::websocket_endpoint` before `manager.connect()`. Why might it reject the connection despite the room/player being created via HTTP just before? Check Redis state within the container during the test run.
    - Check logs from the `infra-backend-test-1` container (`docker logs infra-backend-test-1`) for specific rejection reasons or errors during the handshake.
  - **Event Loop Closed:**
    - Investigate potential issues with `pytest-asyncio` event loop scoping, although the error occurs during a standard `httpx` POST, not necessarily deep in async fixture management.
    - Could the reuse of the session-scoped `integration_client` across tests, or complex nesting of `async with aconnect_ws` in the second test, be causing issues with the underlying connection pool or loop state after the first test completes or during the second test's setup/execution?
    - Check server logs for errors related to the second test's execution.
    - Simplify `test_websocket_player_join_broadcast_integration` to isolate the failing step (e.g., does only the first POST fail?).
- **Code Ref:** `tests/integration/test_websocket_integration.py`, `tests/integration/conftest.py`, `backend/routes/rooms.py`

---

## 🐞 Item: Missing WebSocket Message Handlers (selectPlane, startRound, etc.)

- **Context:** The `_recv_loop` within `backend/routes/rooms.py::websocket_endpoint` currently only has basic logic for `ping`/`pong` and a placeholder for `guess`. Crucial game logic handlers for messages like `selectPlane`, `startRound`, `skipRound`, `transferHost`, `claimHost`, and `leave` are missing.
- **Potential issues:** Core game functionality cannot proceed. Hosts cannot select planes or start rounds, players cannot leave cleanly via WS, etc.
- **Why accepted:** Initial focus was on connection management and basic message flow.
- **Next step:** Implement handlers for each missing message type within the `elif` chain in `_recv_loop`, interacting with `room_service` and `manager` as needed. Prioritize `selectPlane` and `startRound` for core gameplay testing.
- **Code Ref:** `backend/routes/rooms.py#L633` (Start of `_recv_loop`)

---

## ⛳ Item: Flight Route Enrichment via AeroAPI

- **Context:** The ingest service (`backend/ingest/enrichment.py`) uses FlightAware's AeroAPI (`/flights/{hex_ident}`) to fetch origin and destination airport ICAO codes for flights, supplementing data from OpenSky.
- **Potential issues:** Relies on a free tier AeroAPI key (`FLIGHTAWARE_API_KEY`) which may have usage limits. The lookup by hex ID might occasionally return multiple flights or fail for specific aircraft (e.g., military, very recent flights not yet fully processed by FlightAware). Error handling and caching (6hr TTL) are in place, but heavy usage could exceed free tier limits.
- **Why accepted:** Provides the necessary origin/destination data for the core game mechanic, which was unavailable via the free OpenSky endpoint. Free tier is sufficient for development and personal use.
- **Next step:** Monitor API usage. If limits are hit, investigate paid tiers or alternative data fusion strategies. Refine logic for handling ambiguous responses from `/flights/{hex_ident}` if necessary.
- **Code Ref:** `backend/ingest/enrichment.py#L124` (Location of `fetch_aeroapi_route` function)

---

## ⛳ Item: Placeholder Distance Calculation in Scoring

- **Context:** The `calculate_distance_km` function in `backend/services/scoring.py` uses a very rough approximation based on latitude/longitude differences.
- **Potential issues:** Scoring in Distance mode will be inaccurate and potentially unfair.
- **Why accepted:** Allows testing the Distance scoring mode logic flow without implementing full geographic calculations and airport data loading immediately.
- **Next step:** Replace the placeholder with a proper geodesic distance calculation using a library like `geopy`. This also requires implementing the `get_airport_coords` function to fetch real coordinates, likely from a cached airport dataset.
- **Code Ref:** `backend/services/scoring.py#L47`

---

## ⛳ Item: Plane Selection Logic Placeholder

- **Context:** The `selectPlane` handler in `backend/routes/rooms.py` currently uses placeholder values (`BOS`, `destination`) for the correct airport code and guess direction. It also doesn't validate the selected plane hex against currently tracked aircraft.
- **Potential issues:** The game cannot function correctly as the correct answer isn't determined from live/sample data. Invalid plane selections are possible.
- **Why accepted:** Allows implementing the round state machine and message flow without integrating the plane data lookup logic from the ingest service immediately.
- **Next step:** Modify the `selectPlane` handler to:
  1. Fetch the selected plane's data (e.g., from `plane:{hex}` in Redis).
  2. Validate that the plane exists and has origin/destination data.
  3. Determine the correct `correct_airport_code` (origin or destination based on flight phase/direction).
  4. Determine the `guess_direction` to send to clients.
- **Code Ref:** `backend/routes/rooms.py#L498`

---

## ⛳ Item: WebSocket Delta Message Compression

- **Context:** The `backend/services/broadcast.py` background task sends `delta` WebSocket messages containing plane updates. Currently, these messages are sent as uncompressed JSON.
- **Potential issues:** Large numbers of planes or frequent updates could lead to significant bandwidth usage, potentially exceeding the 5 kB/s target mentioned in the PRD for low-bandwidth environments (like a home Pi).
- **Why accepted:** Implementing standard WebSocket compression (permessage-deflate) requires potentially switching WebSocket libraries or adding complex middleware, adding significant effort upfront. Monitoring actual payload sizes during testing is needed first.
- **Next step:** Monitor the size of broadcasted delta messages during integration/load testing. If average or peak sizes exceed thresholds (e.g., >1-2KB consistently), investigate adding permessage-deflate compression, potentially using the `websockets` library directly instead of FastAPI's built-in handling, or exploring FastAPI/Starlette middleware options.
- **Code Ref:** `backend/services/broadcast.py` (TODO comment within `broadcast_plane_updates` function)

---

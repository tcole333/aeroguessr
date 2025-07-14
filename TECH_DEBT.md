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

## ✅ Item: WebSocket Message Handlers (COMPLETED)

- **Context:** All WebSocket message handlers for core game functionality are now fully implemented in `backend/routes/rooms.py::websocket_endpoint`.
- **Implemented handlers:**
  - `ping`/`pong` - Bidirectional heartbeat messages
  - `guess` - Player guessing with validation and race condition handling
  - `selectPlane` - Host plane selection with data fetching and validation
  - `startRound` - Host round starting with state transitions and broadcasting
  - `skipRound` - Host round skipping with state reset
  - `transferHost` - Host privilege transfer with validation
  - `claimHost` - Host claiming after disconnect with timing validation
  - `leave` - Clean player departure
- **Status:** All core game functionality is working. Solo mode has separate handling.
- **Code Ref:** `backend/routes/rooms.py` lines 946-1657 (Complete message handling implementation)

---

## ✅ Item: Flight Route Enrichment via AeroAPI (COMPLETED)

- **Context:** The ingest service (`backend/ingest/enrichment.py`) uses FlightAware's AeroAPI (`/flights/{hex_ident}`) to fetch origin and destination airport ICAO codes for flights, supplementing data from OpenSky.
- **Potential issues:** Relies on a free tier AeroAPI key (`FLIGHTAWARE_API_KEY`) which may have usage limits. The lookup by hex ID might occasionally return multiple flights or fail for specific aircraft (e.g., military, very recent flights not yet fully processed by FlightAware). Error handling and caching (6hr TTL) are in place, but heavy usage could exceed free tier limits.
- **Why accepted:** Provides the necessary origin/destination data for the core game mechanic, which was unavailable via the free OpenSky endpoint. Free tier is sufficient for development and personal use.
- **Next step:** Monitor API usage. If limits are hit, investigate paid tiers or alternative data fusion strategies. Refine logic for handling ambiguous responses from `/flights/{hex_ident}` if necessary.
- **Code Ref:** `backend/ingest/enrichment.py#L124` (Location of `fetch_aeroapi_route` function)

---

## ✅ Item: Distance Scoring Implementation (COMPLETED)

- **Context:** Distance scoring is fully implemented with proper geographic calculations and a comprehensive airport dataset.
- **Implemented features:**
  - `calculate_distance_km` - Uses proper haversine formula for great-circle distance calculations
  - `get_airport_coords` - Retrieves airport coordinates from a comprehensive dataset
  - `calculate_distance_score` - Implements linear scoring based on distance (100 points at 0km, 0 points at 1000km)
  - Airport database with ~500K airports loaded from `sample_data/airports_min.json`
  - Fallback dataset for core airports (BOS, JFK, PVD, etc.)
- **Status:** Distance mode fully functional with accurate geographic calculations.
- **Code Ref:** `backend/services/scoring.py`, `backend/utils/geo.py`, `backend/utils/airport_db.py`

---

## ✅ Item: Plane Selection Logic Implementation (COMPLETED)

- **Context:** The `selectPlane` handler in `backend/routes/rooms.py` is fully implemented with proper plane data validation and route determination.
- **Implemented features:**
  - Fetches selected plane data from Redis (`plane:{hex}`)
  - Validates plane exists and has origin/destination data
  - Determines correct airport code based on flight route data
  - Determines guess direction (origin vs destination) based on flight phase
  - Sends confirmation message to host with selected plane details
  - Proper error handling for invalid plane selections
- **Status:** Plane selection fully functional with live flight data integration.
- **Code Ref:** `backend/routes/rooms.py` lines 1179-1333 (Complete selectPlane implementation)

---

## ⛳ Item: WebSocket Delta Message Compression

- **Context:** The `backend/services/broadcast.py` background task sends `delta` WebSocket messages containing plane updates. Currently, these messages are sent as uncompressed JSON.
- **Potential issues:** Large numbers of planes or frequent updates could lead to significant bandwidth usage, potentially exceeding the 5 kB/s target mentioned in the PRD for low-bandwidth environments (like a home Pi).
- **Why accepted:** Implementing standard WebSocket compression (permessage-deflate) requires potentially switching WebSocket libraries or adding complex middleware, adding significant effort upfront. Monitoring actual payload sizes during testing is needed first.
- **Next step:** Monitor the size of broadcasted delta messages during integration/load testing. If average or peak sizes exceed thresholds (e.g., >1-2KB consistently), investigate adding permessage-deflate compression, potentially using the `websockets` library directly instead of FastAPI's built-in handling, or exploring FastAPI/Starlette middleware options.
- **Code Ref:** `backend/services/broadcast.py` (TODO comment within `broadcast_plane_updates` function)

---

## ✅ Item: Browser Refresh Rejoin Functionality (COMPLETED)

- **Context:** Players can now rejoin their game sessions after browser refresh, solving a major user experience issue.
- **Implemented features:**
  - Session persistence using Zustand persist middleware with localStorage
  - Automatic rejoin logic on app startup via `useAutoRejoin` hook
  - Connection details persistence (roomCode, wsUrl, nickname, currentView)
  - Error handling for failed rejoin attempts with user feedback
  - Graceful fallback to home page when rejoin fails
  - UI indicators for rejoin status and connection errors
- **Status:** Browser refresh no longer breaks game sessions. Users can seamlessly return to their game.
- **Code Ref:** `frontend/src/hooks/useAutoRejoin.ts`, `frontend/src/store/createRootStore.tsx`, `frontend/src/hooks/useWebSocketManager.ts`

---

## ✅ Item: Leaderboard Real-time Updates (COMPLETED - Issue #65)

- **Context:** The leaderboard wasn't updating in real-time when players joined or left the room. This was accompanied by a more serious issue where host transfer wasn't working properly.
- **Implemented features:**
  - Added `playerJoined` and `playerLeft` WebSocket message handlers in frontend
  - Implemented `addPlayer` and `removePlayer` actions in game slice
  - Fixed WebSocket auto-reconnect issue preventing proper disconnection (added `isIntentionalClose` flag)
  - Fixed backend immediate host transfer when host leaves
  - Fixed critical backend bug where host validation used stale connection-scoped variables
- **Backend Host Validation Fix:**
  - Problem: Each WebSocket connection had its own `is_host` variable set at connection time
  - This variable wasn't updated during automatic host transfers, preventing new hosts from performing actions
  - Solution: Added `_check_is_host()` helper that dynamically queries Redis for current host status
  - Updated all host-only commands (`selectPlane`, `startRound`, `skipRound`, `transferHost`) to use dynamic check
- **Status:** Leaderboard updates in real-time and host transfer works seamlessly without page refresh.
- **Code Ref:**
  - Frontend: `frontend/src/hooks/useWebSocketManager.ts`, `frontend/src/features/game/gameSlice.ts`
  - Backend: `backend/routes/rooms.py` lines 858-861 (_check_is_host), various handler updates

---

## ⛳ Item: Improved Flight Enrichment System (V2)

- **Context:** Replaced the original AeroAPI-based enrichment with a new two-stage system that combines OpenSky flight data with FlightAware schedule lookups. This addresses limitations in both APIs when used individually.
- **Implementation:**
  - **Stage 1 - OpenSky Flights**: Fetches recent flights by ICAO24 hex (last 24h), providing callsigns with timestamps
  - **Stage 2 - FlightAware Schedule**: Looks up schedules by callsign to get origin/destination/aircraft info
  - **Caching Strategy**: Two-tier Redis caching with 24h TTL for enrichment data and configurable schedule refresh
  - **Fallback Logic**: Gracefully handles partial data, using OpenSky-only data when FlightAware lookups fail
- **Key improvements:**
  - More reliable data by cross-referencing multiple sources
  - Better handling of edge cases (military flights, private aircraft, API failures)
  - Configurable via `ENRICHMENT_V2_ENABLED` and `FLIGHT_SCHEDULE_REFRESH_HOURS` environment variables
  - Maintains backward compatibility with V1 enrichment
- **Potential issues:**
  - Still relies on free tier API limits for both services
  - Schedule lookups may miss very recent flight plan changes
  - Some aircraft (especially GA/military) may lack schedule data entirely
- **Next steps:**
  - Monitor API usage patterns and cache hit rates
  - Consider adding more data sources (e.g., ADS-B Exchange, FlightRadar24 APIs)
  - Implement smarter caching based on flight patterns (e.g., longer TTL for scheduled commercial flights)
- **Code Ref:** `backend/ingest/enrichment_v2.py`, `backend/ingest/enrichment.py` (EnrichmentService class)

---

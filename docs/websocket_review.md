# WebSocket Implementation Review (2025-04-27)

This document summarizes the findings of a review comparing the WebSocket implementation against the project requirements (PRD), existing code, and logs.

## 1. Desired Functionality (Summary from PRD)

- **Connection:** REST join -> WS upgrade (`/ws/{room_code}/{nickname}`).
- **State:** Redis-backed room, player, and round state.
- **Real-time:** Frequent `delta` broadcasts (planes), specific messages for game events.
- **Client->Server:** `ping`, `guess`, `selectPlane`, `startRound`, `skipRound`, `transferHost`, `leave`, (`claimHost` mentioned).
- **Server->Client:** `stateSync`, `delta`, `roundStart`, `roundResult`, `playerJoined`, `playerLeft`, `newHost`, `pong`, `error`.
- **Resilience:** Ping/pong, reconnect handling.

## 2. Current Implementation Assessment & Gaps

### 2.3 WebSocket Schema vs. Implementation (`docs/ws_schema.yaml`, `backend/schemas/ws.py`)

- **Outdated Schema:** `docs/ws_schema.yaml` is significantly out of sync with the Pydantic models in `backend/schemas/ws.py`.
- **Missing Messages:** Schema lacks definitions for `ClaimHostMessage` and `PlaneSelectedConfirmMessage`.
- **Inconsistent Payload Definition:** The structure for `DeltaPayload.planes` differs between the schema/`broadcast.py` helper (`{"updated": [...], "removed": [...]}`) and the actual Pydantic model in `ws.py`. The helper structure in `broadcast.py` seems more appropriate.
- **Minor Type Mismatches:** Timestamp types differ slightly (float vs. int/ms).
- **TODO:**
  - Update `docs/ws_schema.yaml` to accurately reflect _all_ message types and payload structures defined in `backend/schemas/ws.py`.
  - Standardize the `DeltaPayload.planes` structure between `ws.py` and `broadcast.py` (recommend using the `{"updated": ..., "removed": ...}` structure).
  - Align timestamp types/descriptions.

### 2.4 Unimplemented/Untested Functionality (Based on PRD comparison)

- **Client->Server:** `skipRound` message handling appears unimplemented in `rooms.py`. `claimHost` is defined in `ws.py` but its handling logic in `rooms.py` needs verification/implementation according to PRD rules (2-min window).
- **Server->Client:** Initial `stateSync` is correctly sent on connect (verified by integration tests).
- **Resilience:** Ping/pong logic exists in `rooms.py`, but client-side reconnect logic (back-off, queuing) is frontend-specific and not reviewed here. Server-side handling of host disconnects (transfer/auto-randomize) needs robust implementation and testing in `rooms.py`.

### 2.5 Recent Fix (2025-04-27)

During integration testing a duplicate `guess` handler in `backend/routes/rooms.py` was discovered. The first (placeholder) branch consumed incoming `guess` messages, preventing the real persistence logic from running and leaving `RoundData.guesses` empty. This has now been **removed**, and the integration test `test_websocket_player_guess_integration` passes, confirming guesses are correctly saved to Redis.

### 2.6 Recent Fix (2025-04-28)

Added immediate `playerLeft` broadcast upon receiving a client `leave` message, with duplicate-guard in cleanup to prevent double emissions.

## 3. Next Steps

3.  **Align Schemas:** Update `docs/ws_schema.yaml` and standardize the `DeltaPayload` structure.
4.  **Implement Missing Logic:** Add handlers for `skipRound`, `claimHost`, ensure `stateSync` is sent, and fully implement host disconnect/transfer rules.
5.  **Testing:** Add/improve integration tests covering WebSocket interactions, especially edge cases like disconnects, host transfers, and concurrent actions.

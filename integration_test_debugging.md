## Integration Test Debugging Log (As of `make integration-test` after Output 15)

**Overall Status:** 3 tests failing out of 26 total integration tests.

### Key Fixes Applied So Far:

1.  Corrected `AttributeError` in `test_websocket_heartbeat.py` by using `aconnect_ws` and adding the import. (Passed)
2.  Fixed Pydantic `ValidationError` in `_send_error` in `backend/routes/rooms.py` (enum string vs member).
3.  Corrected WebSocket URL construction in `create_room` and `join_room` in `backend/routes/rooms.py`.
4.  Updated `SELECT_PLANE` handler in `backend/routes/rooms.py`:
    - Uses `initialize_round_data`.
    - Uses `PlaneState` model for deserializing plane data from Redis.
    - Refined `guess_direction` logic with detailed logging (which helped identify further issues).
    - Sends `PLANE_SELECTED_CONFIRM` message.
5.  Updated `test_websocket_host_start_round_integration` to consume `planeSelectedConfirm` before sending `startRound`.
6.  Corrected assertions in `test_websocket_host_select_plane_integration` and its dummy plane data setup.
7.  Added extensive debug logging to `SELECT_PLANE` and `START_ROUND` handlers.
8.  Updated `test_websocket_host_start_round_integration` to log received error messages.
9.  Corrected dummy `PlaneState` data in `test_websocket_host_start_round_integration` to include `origin` and `destination`.
10. Corrected dummy `PlaneState` data in `test_websocket_player_guess_integration` to include `origin` and `destination`.
11. Refactored `guess_direction` conditional logic in `SELECT_PLANE` for clarity.
12. Commented out `use_enum_values = True` in `RoundData.Config` which resolved Pydantic not deserializing string state to `RoundStateEnum` members.
13. Reverted diagnostic change in `GUESS` handler to store full `PlayerGuess` objects.
14. Corrected dummy `PlaneState` data in `test_round_timeout_triggers_result` and `test_round_result_when_all_players_guessed` to include `origin` and `destination`.

### Current Passing Tests (Notable Recent Fixes):

- `test_websocket_host_select_plane_integration`
- `test_websocket_host_start_round_integration`
- `test_websocket_player_guess_integration`
- `test_round_timeout_triggers_result`

### Current Failing Tests & Hypotheses (Output 15):

1.  **`test_websocket_claim_host_success`** (in `tests/integration/test_websocket_logic.py`)

    - **Failure:** `AssertionError: Did not receive newHost message within 5.0s`
    - **Server Log Insight:** Host disconnects. `claimHost` message is received from the claimer. However, no `newHost` message is subsequently logged as being broadcast. The claimer client times out waiting for it.
    - **Hypothesis:** The `WSMessageType.CLAIM_HOST` handler logic in `backend/routes/rooms.py` is either missing, incomplete, or contains a bug preventing it from promoting the new host and broadcasting the `newHost` message as per PRD §3.1.6.

2.  **`test_websocket_claim_host_too_early`** (in `tests/integration/test_websocket_logic.py`)

    - **Failure:** `AssertionError: Did not receive any error message within timeout`
    - **Test Log Insight:** `WARNING ... Received unexpected message type: playerLeft`
    - **Hypothesis:** The test client attempts to claim host too early. It expects an `error` message with `ErrorCode.CLAIM_HOST_TOO_EARLY`. However, it first receives a `playerLeft` message (from the original host disconnecting). The test isn't robust enough to handle/ignore this `playerLeft` message before checking for the expected error. The server-side logic to send `ErrorCode.CLAIM_HOST_TOO_EARLY` also needs to be implemented or verified.

3.  **`test_round_result_when_all_players_guessed`** (in `tests/integration/test_websocket_rounds.py`)
    - **Failure:** `TimeoutError` (Test client times out waiting for `roundResult` message via `_wait_for_message` helper).
    - **Test Logic:** Host + 1 player join, host starts round, both players send a guess. Test expects `roundResult` quickly.
    - \*\*Server Log Insight (Output 13, room `UZOC` - pattern should be similar):
      - `SELECT_PLANE` and `START_ROUND` seem successful. `RoundData.state` becomes `ACCEPTING_GUESSES`.
      - First guess (from `player_all`) is logged, `guesses` dict in `RoundData` (before save) contains this guess.
      - Second guess (from `host_all`) is logged, `guesses` dict in `RoundData` (before save) contains both guesses.
      - The logging for the "all players guessed" check (`connected_player_nicks.issubset(current_round_data_local.guesses.keys())`) shows it being TRUE and `_end_round(initiator="all_guessed")` is scheduled as a task.
      - However, the test client times out waiting for `roundResult`.
    - **Hypothesis:**
      - The `asyncio.create_task(_end_round(initiator="all_guessed"))` might have an issue. If `_end_round` itself has an unhandled exception, the task might fail silently without the main WebSocket connection knowing, and `roundResult` is never broadcast.
      - Alternatively, `_end_round` is called, but there's an issue within its logic (e.g., fetching data for scoring, the scoring calculation itself, or broadcasting `roundResult`) that causes it to not complete or fail silently.

### README Updates:

- No critical README updates seem necessary based on the fixes applied so far.

### Next Steps:

1.  **Debug `test_round_result_when_all_players_guessed`:**

    - Add comprehensive logging inside the `_end_round` function in `backend/routes/rooms.py`. Log entry, fetched data (room meta, all players, round data), results of scoring calculations, and right before broadcasting `roundResult` and any `delta` for scores.
    - This will help determine if `_end_round` is being called as expected and if it completes its logic or errors out internally.

2.  **Address `claimHost` tests (`test_websocket_claim_host_success`, `test_websocket_claim_host_too_early`):**

    - **Implement `WSMessageType.CLAIM_HOST` handler:** In `backend/routes/rooms.py`, add the `elif ws_msg.type == WSMessageType.CLAIM_HOST:` block.
      - Refer to PRD §3.1.6: "If the host is disconnected > 2 min, any player may claim host; at 5 min server auto-randomises."
      - The handler should check `room_meta.host_disconnected_ts` against `HOST_DISCONNECT_CLAIM_WINDOW_SECONDS`.
      - If claim is valid: update `room_meta.host_nickname` to `nickname` of claimer, clear `host_disconnected_ts`, save `room_meta`.
      - Broadcast `newHost` message with the new host's nickname.
      - Cancel any pending auto-transfer or claim window timers for the old host.
    - **Implement `ErrorCode.CLAIM_HOST_TOO_EARLY`:** Ensure the `CLAIM_HOST` handler sends this error if a claim is attempted before the window is open.
    - **Make `test_websocket_claim_host_too_early` robust:** Modify the test to properly consume any `playerLeft` messages before asserting the `error` message for `CLAIM_HOST_TOO_EARLY`.

3.  **Review Host Disconnect & Auto-Transfer Logic:**

    - The `_handle_host_disconnect` and `_auto_transfer_host` functions (and associated timers `host_disconnect_check_task`, `auto_transfer_host_task`) need to be carefully reviewed and tested to ensure they interact correctly with the new `claimHost` manual claiming mechanism.
    - Specifically, the 5-minute auto-randomize needs to be verified if no one claims host.

4.  **General Code Review & Refinement:**
    - Review all recent changes for clarity, error handling, and adherence to project standards.
    - Ensure all TODOs related to mocked data in handlers (like in `SELECT_PLANE`) are tracked in `TECH_DEBT.md` if not addressed immediately.

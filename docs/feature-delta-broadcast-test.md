### Goal

Implement **Priority 3** from `docs/backend_testing_plan.md`: verify server‐side plane `delta` WebSocket broadcasts via an integration test.

### Background & Current Coverage

- Integration test suite already covers connection lifecycle, ping/pong, player join/leave, host actions, round timers, and scoring.
- **Gap:** No test confirms periodic `delta` messages reflecting Redis plane state changes (`updated`, `removed`).
- Broadcast logic lives in `backend/services/broadcast.py` and runs continuously inside the backend container (interval = 1 s).

### Proposed Test Scenarios (Happy-Path)

| #   | Description                               | Redis Manipulation                               | Expected `delta` Payload                                                          |
| --- | ----------------------------------------- | ------------------------------------------------ | --------------------------------------------------------------------------------- |
| 1   | Add two new planes after client connects. | `SET plane:<hex>` for A & B.                     | `planes.updated` contains both full `PlaneState` objects; `planes.removed == []`. |
| 2   | Update altitude of plane A.               | `HSET plane:<A> alt=<new>` or replace full JSON. | Next `delta.planes.updated` list includes **only** plane A with new values.       |
| 3   | Remove plane B.                           | `DEL plane:<B>`                                  | Next `delta.planes.removed` list contains `<B>`; `updated` may be empty.          |

Each step should succeed within a generous timeout (≤ 5 s) given broadcast interval.

### Deliverables

1. **Integration Test** `tests/integration/test_websocket_delta.py` implementing scenarios above, marked `@pytest.mark.integration`.
2. Helper `_await_delta(ws, *, updated_ids=None, removed_ids=None, timeout=5.0)` similar to existing `_wait_for_message` utility.
3. Minor extension to `tests/integration/conftest.py` ● add helper `make_dummy_plane(redis, hex, **kwargs)` if needed (optional).
4. **Docs Update** – Mark Priority 3 ✅ in `docs/backend_testing_plan.md` once test passes reliably.

### High-Level Steps

1. Connect host WebSocket → consume initial `stateSync`.
2. Scenario 1: use fixture Redis client to insert two `PlaneState` JSON blobs (expiry 60 s). Await `delta` and assert both IDs appear in `updated`.
3. Scenario 2: modify JSON for plane A (e.g., `alt + 1000`). Await next `delta` and assert only A in `updated`.
4. Scenario 3: `DEL plane:<B>`; await `delta` with `<B>` in `removed`.
5. Clean-up Redis keys & room keys.

### Acceptance Criteria

- Test passes consistently (< 5 % flake) in CI and locally via `make integration-test`.
- No changes required to application code; if flakiness occurs, consider increasing broadcast interval only within the test environment via env var stub (TBD).
- All additions pass `pre-commit run --all-files`.

### Risks & Mitigations

- **Race Conditions:** Broadcast loop timing may cause an extra `delta` before assertion—tests should loop until expectations met or timeout.
- **Large Payloads:** Assert only identifiers, not full deep-equality of `PlaneState` objects to avoid brittle comparisons.
- **Environment Dependence:** Ensure Redis manipulations occur on same instance as backend (use `integration_redis` fixture that targets `redis-test` service).

### Checklist

- [ ] Write test cases in new file.
- [ ] Run `make integration-test` locally; iterate until green.
- [ ] Update `docs/backend_testing_plan.md` (Priority 3 ➜ Completed).
- [ ] Commit with message `test: add delta plane broadcast integration test`.

# Backend Implementation Review – May 2025

> **Scope**: FastAPI backend (`backend/`) implementation of the Plane Guessing Game.
> The goal of this review is to assess compliance with the Product Requirements
> Document (PRD v1.0), QA-Acceptance Checklist and repository coding standards.

---

## 1. Executive Summary

| Area                  | Status                                                                                        | Notes                                                                                      |
| --------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| REST API (v0)         | ✅ Implemented for all required endpoints including room management and health check          | All PRD §5.2 endpoints implemented and tested.                                             |
| WebSocket Gateway     | ⚠️ Core message handling exists (`stateSync`, `delta`, round flow)                            | Performance & reconnection timers need real-world soak tests; schema file not regenerated. |
| Flight Ingest Service | ✅ Parser, Kalman smoother, enrichment & Redis persistence implemented.                       | KPI tests (≥ 99 % parse rate, heading RMS) still pending.                                  |
| Mock ADS-B Generator  | ✅ `sample_data/adsb_generator.py`, enabled via `FAKE_ADSB=1`.                                | Needs limits (1-3 aircraft, ≤ 10 km radius) & docstrings.                                  |
| Redis Schema          | ✅ Keys match PRD §5.3 (`plane:*`, `room:*`).                                                 | TTL auto-cleanup for **rooms** after inactivity not enforced.                              |
| Scoring               | ✅ Exact & distance formulas implemented with airport lookup and geo utils.                   | All core functionality implemented and tested.                                             |
| Tests & Coverage      | ⚠️ Initial CI coverage setup complete (50% threshold). WebSocket and scoring coverage < 85 %. | Coverage reporting added to CI, needs improvement to reach target.                         |
| Dev Experience        | ✅ `pre-commit`, Ruff, Black configured; Makefile helpers present.                            | All dev tooling and licensing in place.                                                    |

Legend: ✅ Complete   ⚠️ Partial/In progress   ❌ Missing

---

## 2. Detailed Gap Analysis

### 2.1 REST API Endpoints

| Endpoint                         | PRD Status                    | Implementation                                       | Gap / Action |
| -------------------------------- | ----------------------------- | ---------------------------------------------------- | ------------ |
| `POST /api/v0/rooms`             | Required                      | Implemented in `backend.routes.rooms.create_room`.   | None.        |
| `POST /api/v0/rooms/{code}/join` | Required                      | Implemented (`join_room`).                           | None.        |
| `GET /api/v0/rooms/{code}`       | Debug-only                    | ✅ Implemented (v0.1, tests added).                  |
| `DELETE /api/v0/rooms/{code}`    | End room                      | ✅ Implemented (v0.1, tests added).                  |
| `GET /api/v0/airports/search`    | Removed after preload per PRD | Not implemented. OK.                                 |
| `GET /healthz`                   | Required                      | Implemented. Could add Redis ping for deeper health. |

### 2.2 WebSocket Messages

Implemented message schemas (`backend/schemas/ws.py`) cover all PRD types except:

- `claimHost` (client→server) — payload class present but handler logic absent in
  `backend.routes.rooms`.
- `pong` (server→client) — not explicitly sent; heartbeat replies missing.
- Error codes need consolidation & documentation sync with `docs/ws_schema.yaml`.

### 2.3 Game Logic Rules

| Rule (PRD §3 & §5)                                   | Implementation Evidence                                                     | Gap                                           |
| ---------------------------------------------------- | --------------------------------------------------------------------------- | --------------------------------------------- |
| Round timeout configurable 10-120 s                  | `RoomMeta.round_timeout_seconds` validated.                                 | OK                                            |
| Host disconnect > 2 min → claim, 5 min → auto-random | Timers `_allow_claim_host` / `_auto_transfer_host` exist.                   | Need integration test & edge-cases.           |
| Room TTL 60 ± 5 min inactivity                       | Not enforced; Redis `expire` for `room:*` keys is static 1 h from creation. | Add activity-based expiry reset.              |
| Scoring formulas                                     | `services/scoring.py` exists.                                               | Real airport coords + distance tests missing. |

### 2.4 Flight Ingest KPI (QA-§2)

| KPI                              | Implementation / Tests                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------------------------- |
| ≥ 99 % parse success             | `tests/backend/ingest/test_parser.py` covers sample file; need full 1-min dump (`adsb_1min.sbs`). |
| Redis key expiry 5 ± 1 min       | `PLANE_TTL_SECONDS` env var default 300 s; test missing.                                          |
| Heading RMS < 30°                | Kalman smoother implemented, but metric not measured.                                             |
| Enrichment cache hit-rate ≥ 90 % | Cache wrappers implemented; replay test pending.                                                  |

### 2.5 QA-Acceptance Checklist Status

| ID  | Item                                            | Status                                                  |
| --- | ----------------------------------------------- | ------------------------------------------------------- |
| 0-1 | LICENSE file (MIT)                              | ✅ Present and valid                                    |
| 0-2 | README quick-start spin-up (backend + frontend) | ⚠️ Docker compose exists in infra/, untested.           |
| 0-3 | `.env.example` contains all vars                | ⚠️ File present but list vs PRD needs diff.             |
| 0-4 | sample_data/adsb_1min.sbs & airports_min.json   | ✅ Using synthetic data generator and airports dataset. |
| 0-5 | ADR/0001-initial.md & `.cursorrules`            | ⚠️ ADR directory created; needs content review.         |
| 0-6 | `pre-commit run --all-files` clean              | ⚠️ Hooks configured; CI run required.                   |
| 1   | CI lint/coverage/image build                    | ⚠️ Coverage workflow added with 50% initial threshold.  |
| 2   | Flight Ingest KPIs                              | See §2.4 — partial.                                     |
| 3   | Mock ADS-B generator env-flag                   | Implemented; needs radius limit check.                  |
| 4   | WS performance tests (50 players)               | Not yet implemented.                                    |
| 5   | Game logic items                                | Partial; see §2.3.                                      |
| 6   | Frontend KPIs                                   | Out of scope for backend review.                        |
| 7   | End-to-End Cypress Smoke                        | Not implemented.                                        |

---

## 3. Test Coverage Snapshot

```bash
$ pytest -q
✖  Collected ### tests, coverage report missing in CI.
```

Manual inspection:

- Ingest: parser, smoother, enrichment, main loop heavily tested (≈400 lines).
- Routes: REST endpoints tested with `fakeredis` + httpx async.
- WebSocket: only ad-hoc `test_websocket_debug.log`; no automated tests.
- Scoring: zero tests.

Action: add `pytest-cov` + GitHub Action step, target ≥ 85 % backend.

---

## 4. Recommendations & Next Steps

1. **Test Coverage Improvement (Current: 51%)**

   - Focus on low coverage areas:
     - `backend/routes/rooms.py` (15%)
     - `backend/utils/connection_manager.py` (28%)
     - `backend/services/broadcast.py` (40%)
     - `backend/app.py` (46%)
   - Add unit tests incrementally to reach 85% target
   - Integration tests excluded from CI coverage for now

2. **CI & Metrics**

   - ✅ Coverage reporting added to CI (50% threshold)
   - Set up Codecov integration and badge
   - Enable mypy strict mode
   - Add pre-commit checks to CI pipeline

3. **Game logic polish**

   - Add WebSocket heartbeat (`ping`/`pong`)
   - Implement `claimHost` flow tests
   - Add room inactivity TTL

4. **Ingest KPIs**

   - Write integration test for sample data replay
   - Implement cache hit-rate metrics
   - Add heading variance calculations

5. **Documentation**

   - Review and update ADR content
   - Regenerate API and WebSocket schemas
   - Update `.env.example` with all required variables

6. **Additional Items After Front End Spec Review**

- Game State on Reconnect/Join-in-Progress: The frontend needs a way to obtain the current game state if a player reconnects or joins late. For example, if a player refreshes the page in the middle of a round, or if a new player is allowed to join an ongoing game (even if just to spectate), the server should provide the current round info and scores. Currently, the schema may not specify this. A solution is to introduce a state sync mechanism: either an HTTP endpoint like GET /rooms/{code}/state that returns the ongoing game state (current round number, time remaining, plane data, scores, etc.), or have the WebSocket send a snapshot upon (re)connection. For instance, the server could re-send the latest round_start (or use a Pusher-like cache channel that automatically sends the last event to new connections​). This way the frontend can seamlessly restore the UI after a reconnect without waiting for the next event.
- Round Timing Details: The OpenAPI/WebSocket schema should explicitly provide timing information for rounds. If the PRD says each round is X seconds, the backend still needs to communicate that to the client (in case it changes or for flexibility). If the current contract lacks a field for round duration or start time in the round start message, that’s a missing piece. Proposed fix: include a timestamp or duration in the round_start event (e.g. { round: 2, plane: {...}, duration: 30 }). This ensures the frontend timer is in sync and knows when to stop accepting guesses.
- Game Start Trigger: If the PRD expects a manual start by the host but the API has no endpoint or message for it (for example, if currently the game starts immediately when two players join, but the PRD wanted a “Start” button), then we need a start game command. The fix could be adding a REST endpoint POST /rooms/{code}/start or a WS message that the host client sends. Conversely, if the game should auto-start but the backend doesn’t send a clear game_started event, the frontend might be stuck guessing when to transition. In that case, ensure a dedicated event (or an overloaded use of round_start as the cue) to signal the transition from lobby to game.
- Player List on Join: The frontend lobby will need the current list of players upon entering. If the WebSocket join confirmation currently does not include the existing players (and only sends incremental join/leave events), the client might not know who was already in the room. A missing functionality would be an initial players list snapshot. To fix this, the join response (via HTTP or the first WS message) should carry the list of active players (names or IDs). That way the lobby can be populated immediately. (This is analogous to how presence channels provide a full member list on subscription​
  pusher.com
  .)
- Identifying Returning Players: The backend contract might not clarify how players are identified (perhaps just by name, which the user enters each time). This can be a problem if a player disconnects and rejoins – they might appear as a new entry unless the backend has a reconnection mechanism. If not already present, consider using a unique player identifier (maybe assigned at join and stored in local storage or a cookie) so that if the same person rejoins, the backend can recognize them and restore their score. Without this, the frontend can’t fully “reconnect” a player to their prior state. Proposed fix: include a stable player ID in join responses and require it on rejoin attempts, or use a session token.
- Missing Game End Signal: It needs to be absolutely clear when the game is over. If the current implementation lacks a distinct game_over event or a flag in the final round’s message, the frontend might not know to show the final results as final. We should add a explicit indicator. For example, add "finalRound": true in the round end event for the last round, or have a separate game_over event with perhaps a summary. This will prompt the frontend to show the end-of-game screen and not expect further rounds.
- Plane Data Enrichment Timing: The schema might currently send plane data either with full info always or partial info always. To support the game properly, the backend should send partial plane info at round start (excluding the answer detail) and full info at round end. If the backend is instead sending full info immediately (including the plane’s model/type), that would spoil the game. The contract should be adjusted so that either the sensitive field is null/omitted in round_start or a separate “clue” object is sent. The frontend will then only show what it’s given (which should be the non-spoiler data). At reveal time, the answer is provided. If currently the backend does not differentiate these or fails to send the enriched info at all, that’s a flaw: ensure the round_end includes the needed fields (aircraft type name, etc.).
- Guess Validation/Format: Depending on how the backend checks answers, the API might need to provide the list of acceptable answers or a format. If the PRD says “guess the aircraft model”, the backend likely expects a specific naming (like “Boeing 767” vs “767-300”). If there’s no support for partial credit or variant matching, it’s fine, but the frontend might benefit from knowing acceptable values to assist the user (like an autocomplete of plane models). If such support is not in v1, it’s not critical, but worth noting that currently the backend expects an exact string. A potential improvement (not necessarily for v1) is an API to fetch valid aircraft types or an endpoint like GET /planes/types that the frontend could use to populate a dropdown.

---

## 5. Sign-off Checklist (post-gap-fix)

- [ ] All QA-0 items pass locally.
- [ ] REST & WS endpoints align with PRD; schemas regenerated.
- [ ] Backend test coverage ≥ 85 %.
- [ ] CI passes linting, tests, image build < 3 min.
- [ ] Room inactivity TTL & host-handoff timers validated via integration test.
- [ ] Ingest service meets parse, variance & cache-hit KPIs.

---

_Prepared by: AI Code Review Assistant – May XX 2025_

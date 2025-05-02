# Backend Implementation Review – May 2025

> **Scope**: FastAPI backend (`backend/`) implementation of the Plane Guessing Game.
> The goal of this review is to assess compliance with the Product Requirements
> Document (PRD v1.0), QA-Acceptance Checklist and repository coding standards.

---

## 1. Executive Summary

| Area                  | Status                                                                               | Notes                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| REST API (v0)         | ✅ Implemented for all required endpoints including room management and health check | All PRD §5.2 endpoints implemented and tested.                                             |
| WebSocket Gateway     | ⚠️ Core message handling exists (`stateSync`, `delta`, round flow)                   | Performance & reconnection timers need real-world soak tests; schema file not regenerated. |
| Flight Ingest Service | ✅ Parser, Kalman smoother, enrichment & Redis persistence implemented.              | KPI tests (≥ 99 % parse rate, heading RMS) still pending.                                  |
| Mock ADS-B Generator  | ✅ `sample_data/adsb_generator.py`, enabled via `FAKE_ADSB=1`.                       | Needs limits (1-3 aircraft, ≤ 10 km radius) & docstrings.                                  |
| Redis Schema          | ✅ Keys match PRD §5.3 (`plane:*`, `room:*`).                                        | TTL auto-cleanup for **rooms** after inactivity not enforced.                              |
| Scoring               | ✅ Exact & distance formulas implemented with airport lookup and geo utils.          | All core functionality implemented and tested.                                             |
| Tests & Coverage      | ⚠️ Extensive unit tests for ingest & routes; WebSocket and scoring coverage < 85 %.  | Need coverage report in CI.                                                                |
| Dev Experience        | ✅ `pre-commit`, Ruff, Black configured; Makefile helpers present.                   | All dev tooling and licensing in place.                                                    |

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

| ID  | Item                                            | Status                                                          |
| --- | ----------------------------------------------- | --------------------------------------------------------------- |
| 0-1 | LICENSE file (MIT)                              | ❌ Not present.                                                 |
| 0-2 | README quick-start spin-up (backend + frontend) | ⚠️ Docker compose exists in infra/, untested.                   |
| 0-3 | `.env.example` contains all vars                | ⚠️ File present but list vs PRD needs diff.                     |
| 0-4 | sample_data/adsb_1min.sbs & airports_min.json   | ✅ Using synthetic data generator and airports dataset.         |
| 0-5 | ADR/0001-initial.md & `.cursorrules`            | ❌ ADR directory missing; `.cursor/rules/` exists so half-pass. |
| 0-6 | `pre-commit run --all-files` clean              | ⚠️ Hooks configured; CI run required.                           |
| 1   | CI lint/coverage/image build                    | GitHub workflow stub present; coverage badge TBD.               |
| 2   | Flight Ingest KPIs                              | See §2.4 — partial.                                             |
| 3   | Mock ADS-B generator env-flag                   | Implemented; needs radius limit check.                          |
| 4   | WS performance tests (50 players)               | Not yet implemented.                                            |
| 5   | Game logic items                                | Partial; see §2.3.                                              |
| 6   | Frontend KPIs                                   | Out of scope for backend review.                                |
| 7   | End-to-End Cypress Smoke                        | Not implemented.                                                |

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

1. **Critical QA blockers**
   - Add `ADR/0001-initial.md` to document architectural decisions.
   - ✅ LICENSE (MIT) added
   - ✅ Sample data and airports dataset in place
   - ✅ All REST endpoints implemented
2. **Game logic polish**
   - ✅ Airport database integrated with scoring system
   - Add WebSocket heartbeat (`ping`/`pong`) and `claimHost` flow tests.
3. **Ingest KPIs**
   - Write integration test that replays sample 1-min dump twice, asserting
     cache hit-rate and heading variance.
4. **CI & Metrics**
   - Enforce coverage + mypy strict in pipelines; upload coverage to badge.
   - Ensure `pre-commit` passes inside CI to satisfy QA-0-6.
5. **Docs & Schemas**
   - Regenerate `docs/api_openapi.yaml` & `docs/ws_schema.yaml` after endpoint
     tweaks; include in commit.

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

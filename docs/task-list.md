# Plane Guessing Game – Detailed Task List (v1.0)

_Granularity ≈ 10–15 min per task. Execute top‑to‑bottom; each step unblocks the next._

---

## 0 Initial Setup

- [x] 1. **Create mono‑repo** (`plane‑game/`) with `backend/`, `frontend/`, `infra/`, `.gitignore`.
- [x] 2. Add `README.md` skeleton + project badges.
- [x] 3. Commit `.editorconfig` + Prettier config (JS/TS) + `ruff.toml` (Python linter).
- [x] 4. Generate `.env.example` with CENTER_LAT/LON, Redis URL, etc.
- [x] 5. Set up pre‑commit hooks (black, ruff, prettier).

## 1 Environment & CI

- [x] 6. Add GitHub Actions workflow: _lint_ (Python + Node) on PR.
- [x] 7. Extend workflow: build multi‑arch Docker image (`backend/Dockerfile`).
- [x] 8. Generate SSH deploy key; add to repo secrets (`PI_HOST`, `PI_USER`).
- [Deferred] 9. Write `infra/deploy.sh` (ssh → `docker compose pull && up -d`).
- [Deferred] 10. Add workflow job: on `main` push → deploy script.

## 2 Flight Ingest Service

- [x] 11. Create `backend/ingest/` package with Poetry init //set at the project level now instead.
- [x] 12. Implement SBS‑1 line parser → `RawMessage` dataclass.
- [x] 13. Unit‑test parser with fixture file (pytest).
- [x] 14. Build Redis helper (`redis_async.py`) – `set_json`, `expire`.
- [x] 15. Draft Kalman smoother class (lat/lon/alt – constant‑velocity).
- [x] 16. Wire smoother into ingest loop (async TCP reader → smoother → Redis hash update).
- [ ] 17. Cap trail list to 30 points; store as JSON array.
- [ ] 18. Add enrichment stub (OpenSky REST) w/ 24 h cache.
- [ ] 19. Unit‑test enrichment with HTTPX mock.
- [ ] 20. Add CLI entry `python -m ingest`.

## 3 Backend API Skeleton

- [ ] 21. Scaffold FastAPI app (`backend/app.py`) with uvicorn entry.
- [ ] 22. Add Pydantic models: Plane, Player, RoomMeta.
- [ ] 23. Implement health check `GET /healthz`.
- [ ] 24. Create `rooms_router` with `POST /rooms` (in‑memory stub).
- [ ] 25. Integrate Redis helpers for room meta.
- [ ] 26. Add join endpoint and nickname uniqueness logic.
- [ ] 27. Generate OpenAPI docs (`/docs`).

## 4 WebSocket Gateway

- [ ] 28. Install `fastapi-websocket` extras.
- [ ] 29. Implement `/ws/{room}/{player}` handler skeleton.
- [ ] 30. Send `stateSync` payload on connect (mock data).
- [ ] 31. Add heart‑beat ping/pong (10 s).
- [ ] 32. Write `ConnectionManager` util (broadcast, send_personal).
- [ ] 33. Route `guess` message → echo back `delta` (placeholder).
- [ ] 34. Integration test WS using `websockets` Py client.

## 5 Game Logic Core

- [ ] 35. Implement Redis `room:{code}:players` helpers (join/leave/update).
- [ ] 36. Implement host auto‑transfer timer using `asyncio.create_task`.
- [ ] 37. Code round state machine (`waiting → active → done`).
- [ ] 38. Add scoring module (exact + distance functions).
- [ ] 39. Hook `selectPlane` + `startRound` messages to state machine.
- [ ] 40. Emit `roundStart`, collect guesses, compute results, emit `roundResult`.
- [ ] 41. Add disconnect handler → mark player offline, start 5 min grace timer.

## 6 Plane Broadcast

- [ ] 42. Create async task: every 1 s pull all `plane:*` keys; build `PlaneUpdate[]`.
- [ ] 43. Diff against last sent, send `delta` with only changed planes.
- [ ] 44. Compress payload >1 kB with `gzip` frame.

## 7 Frontend Scaffold

- [ ] 45. Init Vite React TS app in `frontend/`.
- [ ] 46. Install `react-leaflet`, `leaflet`, `fuse.js`, `zustand` (state).
- [ ] 47. Set up ESLint + Prettier config shared via monorepo root.
- [ ] 48. Create `<MapView>` with OSM TileLayer from `.env`.
- [ ] 49. Render dummy plane SVG markers.
- [ ] 50. Implement collapsible panel with `Planes`, `Leaderboard`, `Settings` tabs.
- [ ] 51. Connect WebSocket on load; log incoming messages.
- [ ] 52. Build `useGameStore` (zustand) to hold room state.

## 8 Plane List & Selection

- [ ] 53. Implement fuzzy airport search with Fuse index (airport preload JSON).
- [ ] 54. On map click → highlight plane, open details panel.
- [ ] 55. Plane list click → pan/zoom to marker.
- [ ] 56. Submit guess form → send `guess` WS message.

## 9 Rounds & Scoring UI

- [ ] 57. Show countdown timer (30 s) when `roundStart` arrives.
- [ ] 58. Display guess status chips per player.
- [ ] 59. Animate confetti on score increase.
- [ ] 60. Leaderboard tab – sorted table, highlight leader.
- [ ] 61. Settings tab – night‑mode toggle (CSS var switch).

## 10 Production Hardening

- [ ] 62. Add log rotation config (`logrotate.d/game`).
- [ ] 63. Parameterise Kalman noise via `.env`.
- [ ] 64. Install `cloudflared`; write `infra/tunnel.yml`.
- [ ] 65. Document tail‑scale or LE + DDNS alternatives in README.
- [ ] 66. Build Dockerfile for React static build + Nginx.
- [ ] 67. Add compose service `frontend` serving `/` and proxy `/api` to backend.

## 11 Tests & QA

- [ ] 68. Cypress e2e test: create room, join two players, play one round (stub plane).
- [ ] 69. Load‑test WS with `autocannon` (100 msgs/s) – ensure Pi CPU <40 %.
- [ ] 70. README: write local dev instructions.
- [ ] 71. Tag git `v1.0.0`, push.

---

**End of ordered task list.**

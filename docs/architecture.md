# Architecture

How AeroGuessr is put together: processes, data flow, Redis state, the game engine and the frontend. For what the game must do, see the [PRD](PRD.md). For how it runs on the Pi, see [deployment.md](deployment.md); for running it on your own receiver, [self-hosting.md](self-hosting.md).

## Processes

```text
                      ┌────────────────────────── Docker Compose (infra/) ──────────────────────────┐
 Browser ──HTTPS──▶ Cloudflare Tunnel ──▶ nginx :80 ──┬── /            ──▶ frontend (static build)  │
                                                      └── /api/, /healthz, /readyz ──▶ backend :8000 │
                      │                                      supervisord: api (uvicorn) + ingest     │
                      │                                              │            │                 │
                      │                                            Redis ◀────────┘                 │
                      └──────────────────────────────────────────────────────────────────────────────┘
 dump1090 (host) ──SBS-1 TCP :30003──▶ ingest          ingest ──HTTPS (budgeted)──▶ FlightAware AeroAPI
```

- **nginx** is the only container that publishes a port (80). It proxies `/api/` (REST and WebSocket), `/healthz` and `/readyz` to the backend, and everything else to the frontend. The `location /ws/` block in `infra/nginx.conf` matches no route; WebSocket traffic uses `/api/`.
- **The frontend container** serves the static build with its own nginx (`frontend/nginx/default.conf.template`). That nginx also proxies `/api/`, `/healthz` and `/readyz` to `BACKEND_URL` (default `http://backend:8000`), resolving the backend on each request.
  - In this stack those paths never reach it.
  - The self-hosters' stack (`selfhost/compose.yaml`, see [self-hosting.md](self-hosting.md)) has no separate nginx: the frontend container publishes the port.
- **The backend container runs two processes** under supervisord (`backend/supervisord.conf`), and both log to stdout:
  - `api`: `uvicorn backend.app:app`. It serves REST and the WebSocket, and runs the broadcast loop.
  - `ingest`: `python -m backend.ingest.main`. It reads ADS-B from dump1090, smooths positions, attaches routes and writes planes to Redis.
- **Redis** holds all shared state between the two processes and between WebSocket connections.
- **dump1090** runs on the Pi host, outside Docker. The Pi override (`infra/docker-compose.pi.yml`) points `ADSB_HOST` at `host.docker.internal`.

## Wire contract

The generated schemas are the contract. Read them rather than any table in a doc.

| What | Source of truth | Regenerate |
|---|---|---|
| REST | [`api_openapi.yaml`](api_openapi.yaml) | `make openapi` |
| WebSocket messages | [`ws_schema.yaml`](ws_schema.yaml) | `make ws-schema` |
| Frontend types and zod schemas (`frontend/types/`) | the two YAML files | `cd frontend && npm run gen:schema`, after the `make` targets |

- **REST** lives under `/api/v0`:
  - `GET /config` returns the client config: the receiver's location, the monitored airport, the antenna range, the basemap style, the map credits and the running version (`backend/routes/client_config.py`);
  - `POST /rooms` creates a room;
  - `POST /rooms/{code}/join` joins a room;
  - `POST /rooms/solo/join` creates a solo room.
- **Probes:** `/healthz` (liveness) and `/readyz` (Redis and ingest) sit at the root (`backend/routes/health.py`).
- **Version:** `/healthz` and `GET /config` name the running version, and the in-game settings tab shows it (`backend/version.py`). It is `BUILD_VERSION`, which release images set to their release version (the git tag without its `v`). Otherwise it is `pyproject.toml`'s version, plus the commit in a git checkout, e.g. `0.1.0-alpha.1+1a2b3c4`. An image built without `BUILD_VERSION`, like the Pi's, has no checkout, so it reports the version alone.
- **WebSocket path:** `/api/v0/rooms/ws/{room_code}/{nickname}` (`backend/routes/rooms.py`).
  - Every message is an envelope `{type, payload, ts}`. Types are camelCase, e.g. `selectPlane`, `roundResult`.
  - The create and join responses include a `ws_url`. Its base comes from `WS_BASE_URL` when that is set.

## Game engine

All WebSocket handling is in `backend/routes/rooms.py::websocket_endpoint`. Room and player state go through `backend/services/room_service.py`.

- **Round states** (`backend/schemas/game.py::RoundStateEnum`): `waiting_for_selection` → `accepting_guesses` → `showing_results`.
- **Host flow:**
  - The host sends `selectPlane` and then `startRound`. The round ends when everyone has guessed or the timeout expires.
  - The server then scores the round (`backend/services/scoring.py`) and sends `roundResult`. After 5 s it returns to `waiting_for_selection`.
  - The host doesn't change between rounds. Only `transferHost`, a claim or a disconnect changes it.
  - `skipRound` and `transferHost` are host-only.
- **Host checks:** host-only messages (`selectPlane`, `startRound`, `skipRound`, `transferHost`) check the host in Redis (`_check_is_host`), so a host change takes effect immediately for every connection.
- **Disconnected host:**
  - If other players are connected, the host role passes to one of them immediately.
  - If the host left the room empty, a later player may send `claimHost` after `HOST_DISCONNECT_CLAIM_WINDOW_SECONDS` (default 120).
  - After 5 minutes the server picks a connected player itself.
- **Solo mode** is a personal room with no host or rounds. `selectPlane` is followed directly by `guess`, and the plane is stored under `room:{code}:solo_context`.
- **Round targets** (`backend/services/round_target.py`):
  - A plane is playable only when it has a route with the monitored airport (KBOS) at one end, and the other end is in `data/airports.json`.
  - Arrivals ask for the origin; departures ask for the destination.
- **Scoring:** Distance mode gives `round(max(0, 100 − km/10))`; Exact mode gives 100 for the right airport. IATA and ICAO codes for the same airport are equivalent (`backend/utils/airport_db.py`).

### Answer secrecy

No message before `roundResult` may name a route's airports (PRD §5.2).
- Planes go out as `PublicPlaneState`, an allowlist model with `extra="forbid"` built by `backend/services/plane_visibility.py`.
  - It carries a `route_hint` (`guess_direction`, `known_airport`, `eligible`) instead of `origin` and `destination`.
- The frontend derives what to show from the hint in `frontend/src/features/planes/routeDisplay.ts`.
- `tests/integration/test_answer_secrecy.py` checks the wire end to end.
- One leak remains: a second room or a solo session can select a live round's plane and read its answer. It is tracked in #171.

### Broadcast loop

`broadcast_plane_updates` (`backend/services/broadcast.py`) runs in the API process once a second:
1. Publish the count of rooms with a live player (`presence:active_rooms`).
2. Read every `plane:*` key, and delete planes that are out of range or have had no update for `MIN_UPDATE_INTERVAL_SECONDS` (60), unless the plane is in an active round (`backend/services/plane_filter.py`). The Redis TTL is only a backstop.
3. Diff against the last tick and send one `delta` to each room with connections.

There is no Redis pub/sub; the API polls Redis.

## Ingest pipeline

`backend/ingest/main.py`, one process:

1. **Parse.** SBS-1 lines from `ADSB_HOST:ADSB_PORT` go through `backend/ingest/parser.py`. With `FAKE_ADSB=1`, the ingest feeds itself instead (`sample_data/adsb_generator.py`): synthetic planes, unless `FAKE_ADSB_FILE` names a capture to replay.
2. **Smooth.** A constant-velocity Kalman filter in a local ENU frame (`smoother_enu.py`, `PositionSmootherENU`), centred on `CENTER_LAT` / `CENTER_LON`. These default to Logan's coordinates, so set them to the receiver's location; the synthetic feed flies its planes in to the same point.
3. **Route.** Callsigns are matched against an in-memory board of KBOS arrivals and departures (`airport_board.py`). `handle_message` makes no network calls.
4. **Store.** Each plane is written as `plane:{hex}` with a 10-point trail and a TTL of `PLANE_TTL_SECONDS`.
5. **Heartbeat.** `ingest:heartbeat` is written every 5 s, with the feed state. `/readyz` reads it.

### AeroAPI spend

`backend/ingest/aeroapi_client.py` makes the HTTP requests. It reserves budget before each one, and `backend/ingest/board_refresher.py` is its only caller.
- It runs every 15 s, but only while the gate in `enrichment_gate.py` is open. That needs all of:
  - enrichment is enabled;
  - a key is set;
  - `FAKE_ADSB` is off;
  - a player is connected;
  - someone created or joined a room, or sent `selectPlane`, `startRound`, `skipRound` or `guess`, within `ENRICHMENT_IDLE_CUTOFF_MINUTES`.
- Pings and reconnects never count as activity.
- Every request first reserves its pages in Redis (`aeroapi_budget.py`) against a daily cap and a per-minute cap. Any Redis error denies the request. #181 tracks the overcount when a board returns fewer pages than reserved.
- The cap derivation is in `.env.example`. With the defaults it is 25 result sets a day and 8 a minute.

Known limits:
- Overflights, and flights missing from the KBOS boards, get no route and can't be selected.
- The board index is in memory, so restarting the ingest during play costs one cold fetch (about 5 result sets).
- Reservations count `max_pages`, not the pages actually returned, so the daily counter can overstate spend slightly.
- The ingest keeps an in-process floor for today's count. Spend since the last Redis snapshot is forgotten only if Redis and the ingest restart together.

## Redis keys

Every key has a TTL. Production Redis runs `noeviction` (see [deployment.md](deployment.md)), so a key without a TTL would never leave. Keep it that way.

A write that updates an existing key must not recreate it once it is gone: the new key would have no TTL. Either set the TTL in the same atomic write (`SET ... EX`, or HSET and EXPIRE in one MULTI as `add_player` does), or run the read-change-write under WATCH/MULTI so it aborts when the key changed, as `record_guess` and the player updates in `room_service.py` do.

STRING keys hold Pydantic models as JSON (`set_json` / `get_model`); HASH fields hold one JSON model each (read with `hget_model`).

| Key | Type | TTL | Purpose |
|---|---|---|---|
| `plane:{hex}` | STRING (JSON `PlaneState`) | `PLANE_TTL_SECONDS` (300) | Position, velocity, trail, route |
| `room:{code}:meta` | STRING (JSON `RoomMeta`) | 1 h | Mode, timeout, host, created_ts |
| `room:{code}:players` | HASH (`nick` → JSON `Player`) | 1 h | Score, connected, last_seen |
| `room:{code}:round` | STRING (JSON `RoundData`) | 1 h | Round state, selected plane, guesses |
| `room:{code}:solo_context` | STRING (JSON) | 1 h | The solo player's selected plane |
| `ingest:heartbeat` | STRING (JSON `IngestHeartbeat`) | 5 min | Ingest liveness and feed state, read by `/readyz` |
| `presence:active_rooms` | STRING | 10 s | Rooms with a connected player (API → ingest) |
| `presence:last_activity_ts` | STRING | 24 h | Last gameplay action (API → ingest) |
| `aeroapi:result_sets:{YYYY-MM-DD}` | STRING | 3 days | Result sets reserved that UTC day (daily cap) |
| `aeroapi:result_sets_minute:{n}` | STRING | 3 min | Per-minute limiter buckets |
| `aeroapi:usage:{YYYY-MM-DD}` | HASH | 7 days | `{endpoint}:requests` / `{endpoint}:result_sets` |

`RedisClient`'s pool sets connect and reply timeouts (`REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS`, `REDIS_SOCKET_TIMEOUT_SECONDS`, 5 s each by default), so a Redis call that gets no answer fails instead of stalling its caller. A timeout, or a lost connection, can also hit an EXEC that has already run. So the WATCH loops in `room_service.py` retry only when a watched key changed, and otherwise raise (`_execute_watched`): a write is never applied twice.

## Frontend

React 18, TypeScript, Vite, Zustand, Tailwind. The map is Leaflet, with an OpenFreeMap vector basemap rendered by MapLibre (`frontend/src/features/map/`).

- **State:** one store with nested slices (`frontend/src/store/createRootStore.tsx`):
  - `connection`, `planes`, `game`, `ui` and `config`.
  - The store persists the UI preferences, the nickname, the room code and `wsUrl` (localStorage key `plane-session`). `useAutoRejoin` uses them to rejoin after a refresh.
- **WebSocket:** `frontend/src/lib/WebSocketClient.ts`, driven by `frontend/src/hooks/useWebSocketManager.ts`.
  - It pings on a heartbeat and queues outbound messages while disconnected.
  - It reconnects with backoff from 0.5 s to 4 s, plus jitter.
  - Server `error` messages show as sonner toasts with the server's text. A guess refused with `UNKNOWN_AIRPORT_CODE` shows inline in the guess forms instead, and they unlock so the player can guess again.
- **URLs:** API and WebSocket URLs are same-origin.
  - In production nginx routes `/api/` to the backend. Under `npm run dev`, Vite proxies `/api` (with WebSocket upgrade) to the API on `127.0.0.1:DEV_API_PORT` (8000 unless `make demo` picked another).
  - The client connects to the `ws_url` the join endpoints return, and upgrades `ws://` to `wss://` on HTTPS pages.
- **Location:** the app loads the client config (`GET /api/v0/config`) into the `config` slice at startup. The map opens on its centre (the receiver's location rounded to about 1 km, so the exact position stays private), labels its monitored airport in Chart Mode and draws its basemap style, so one build works at any location. Until the config arrives the map shows a placeholder, with a retry if the load failed.
- **Layout:** the panel sits below the map on narrow screens and beside it from Tailwind's `md` breakpoint (768 px). Phase 3 (#176) replaces this layout.
- **Airport data:** autocomplete imports `data/airports.json` through the `@data` alias. It is bundled, not lazy-loaded; #148 tracks lazy loading.

## Configuration

- **Backend:** `backend/settings.py` defines every setting and its default, and code reads them through `get_settings()`.
  - Native runs read the repo-root `.env`, and the process environment wins over it. `AEROGUESSR_ENV_FILE` names another file, or none if empty; the tests read none.
  - Containers read the same root `.env` through Compose's `env_file`, plus container wiring that wins over it (see [deployment.md](deployment.md#environment)).
  - [`.env.example`](../.env.example) lists every setting, and `tests/backend/test_settings.py` checks that it does.
  - An empty environment variable counts as unset and falls through to `.env`, so a blank `FAKE_ADSB=` keeps `.env`'s value. The exception is `FLIGHTAWARE_API_KEY=`, which always means "no key".
  - An invalid value stops the process at startup, except for the AeroAPI spend settings: those keep enrichment off instead.
- **Frontend:** the location and the basemap are backend settings (`CENTER_LAT`, `CENTER_LON`, `MONITORED_AIRPORT_ICAO`, `MAX_ANTENNA_RANGE_KM`, `MAP_STYLE_URL`) that the browser reads from `GET /api/v0/config`. The only build-time variables are `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` (unset: same origin).

## Logging

- **API process:** logs to stderr and to `logs/backend.log`, a 5 MB rotating file with one backup (`backend/app.py`).
  - Loggers run at INFO.
  - Per-tick broadcast lines are DEBUG. Nothing forces DEBUG, which would log every WebSocket frame, answers included.
- **Ingest:** logs to stderr at `LOG_LEVEL` (default INFO), and supervisord merges that into the container's output. Each AeroAPI request logs one INFO line with today's count.
- **On the Pi:** container stdout is capped by Docker (10 MB × 3); see [deployment.md](deployment.md).

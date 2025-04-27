# Plane Guessing Game – Product Requirements Document

### Version 1.0 · April 26 2025 (final consolidated)

---

## 1 Overview & Goals

A casual, real‑time web game where players guess the **other end** of flights overhead at Boston Logan using live ADS‑B signals captured by a Raspberry Pi. One player (the **host**) opens a "room" that friends join on their phones via a four‑letter code—Jackbox‑style. Rounds last about 30 s so the game keeps pace with short‑range aircraft visibility. **Mobile portrait** is the primary form‑factor; the codebase should be modular, easy to extend to a native iOS client later.

**Success criteria**
• A host can run a 5‑round game with up to 10 players on a home‑bandwidth Pi without manual resets.
• >95 % of WebSocket reconnects complete within 3 s, restoring state.
• Average outbound payload per client ≤ 5 kB s⁻¹ at peak play.

---

## 2 Personas & Usage Scenarios

| Persona                       | Scenario                                                                             | Primary Device           |
| ----------------------------- | ------------------------------------------------------------------------------------ | ------------------------ |
| **Travis** (power user, host) | Projects the map on a living‑room TV, controls the game from his phone during a BBQ. | Desktop monitor + iPhone |
| **Jess** (casual guest)       | Scans QR / types room code, plays a few rounds while chatting.                       | iPhone                   |
| **Solo traveller**            | Waiting at the gate in Logan, opens single‑player mode for 10 min.                   | Android phone            |

---

## 3 Gameplay Mechanics

### 3.1 Room lifecycle

1. `POST /rooms` ➜ server returns `room_code` (e.g. _ABCD_).
2. Room is stored in Redis (`TTL = 1 h` since last activity).
3. Players join via `POST /rooms/{code}/join`, pick a unique nickname, upgrade to WebSocket.
4. Host chooses **scoring mode** (Exact / Distance) and **round_timeout** (default 30 s, editable).
5. **Per round**
   a. Host selects an eligible plane.
   b. Server emits `roundStart` with plane ID & timeout, specifying whether to guess _origin_ (arrivals) or _destination_ (departures).
   c. Clients display guess form; one submission per player.
   d. Round ends when all guesses are in **or** timeout expires.
   e. Server scores and emits `roundResult`, updates leaderboard.
6. Host may skip a round or transfer host by command. If the host is disconnected > 2 min, any player may claim host; at 5 min server auto‑randomises.
7. Game ends by host command or when the room empties.

### 3.2 Single‑player mode

Joining the reserved room code `solo` creates a personal room with no round logic—players click any plane and submit guesses immediately.

### 3.3 Scoring

- **Exact mode** – 100 points for correct IATA/ICAO.
- **Distance mode** – `max(0, 100 − distance_km / 10)` (linear taper to zero at 1 000 km). The formula lives in its own module for easy tuning later.

---

## 4 User Experience & Visual Design

- **Mobile‑first portrait**; at ≥600 px viewport the side panel docks left instead of bottom.
- Leaflet map fills the screen. Pinch / two‑finger drag pan works natively.
- Collapsible **Panel** with tabs: **Planes**, **Leaderboard**, **Settings**.
  • **Planes** – list of active flights (callsign, altitude). Selecting pans/zooms map, shows details (altitude, speed, model, airline, SVG icon).
  • **Leaderboard** – live score table; confetti on lead changes.
  • **Settings** – night‑mode toggle, leave room, host controls.
- Plane icons: minimalist SVG; trail rendered as fading polyline (opacity decays over 60 s).
- Airport input uses client‑side fuzzy search (`Fuse.js`) over a 160 kB compressed JSON of worldwide airports for typo‑tolerant autocomplete.

---

## 5 Functional Requirements

### 5.1 Flight ingest, enrichment & smoothing

| Stage           | Tooling                                        | Details                                                                  |
| --------------- | ---------------------------------------------- | ------------------------------------------------------------------------ |
| ADS‑B capture   | `dump1090‑mutability`                          | SBS‑1 lines over TCP 30003.                                              |
| Parser          | Python `asyncio`                               | Parse ➔ `RawMessage` dataclass.                                          |
| Smoothing       | Kalman filter (lat/lon/alt, constant‑velocity) | Prevents jitter & heading flips.                                         |
| Enrichment      | OpenSky REST (auth account)                    | Adds `origin`, `dest`, `type`, `airline`; cached 24 h.                   |
| Redis plane key | `plane:{hex}` HASH                             | `lat,lon,alt,spd,hdg,trail[],origin,dest,…`; TTL 5 min after last point. |

### 5.2 Backend API (FastAPI v0)

#### REST

| Method | Path                        | Body                        | Response                     | Notes                               |
| ------ | --------------------------- | --------------------------- | ---------------------------- | ----------------------------------- |
| POST   | `/api/v0/rooms`             | `{nickname, mode, timeout}` | `{code}` + `Location` WS URL | Host creates room                   |
| POST   | `/api/v0/rooms/{code}/join` | `{nickname}`                | `{ws_url}`                   | 409 if duplicate name               |
| GET    | `/api/v0/rooms/{code}`      | –                           | Full room JSON               | Dev/debug only                      |
| DELETE | `/api/v0/rooms/{code}`      | Host token hdr              | 204                          | Ends room                           |
| GET    | `/api/v0/airports/search`   | `?q=`                       | Array                        | Removed after client preload stable |
| GET    | `/healthz`                  | –                           | `{"status":"ok"}`            | Tunnel/K8s probe                    |

#### WebSocket `/ws/{room}/{player}`

Common envelope:

```jsonc
type WSMessage = {
  "type": string,      // see tables below
  "payload": any,
  "ts": number         // epoch ms
}
```

_Client → Server_
| type | payload |
|------|---------|
| `ping` | `{seq}` |
| `guess` | `{airport_code}` |
| `selectPlane` | `{hex}` (host) |
| `startRound` | `{}` (host) |
| `skipRound` | `{}` (host) |
| `transferHost` | `{to}` (host) |
| `leave` | `{}` |

_Server → Client_
| type | payload |
|------|---------|
| `stateSync` | `FullRoomState` |
| `delta` | `{planes?, scores?}` |
| `roundStart` | `{hex, timeout_s, direction}` |
| `roundResult` | `{results[], next_host?}` |
| `playerJoined` | `{nick}` |
| `playerLeft` | `{nick}` |
| `newHost` | `{nick}` |
| `pong` | `{seq}` |
| `error` | `{code, message}` |

### 5.3 Redis Schema

| Key                   | Type | TTL   | Purpose                                                        |
| --------------------- | ---- | ----- | -------------------------------------------------------------- |
| `plane:{hex}`         | HASH | 5 min | Pos, Vel, Origin, Dest, Meta (Callsign, Country, Cat), Trail[] |
| `room:{code}:meta`    | HASH | 1 h   | mode, timeout, host, created_ts                                |
| `room:{code}:players` | HASH | 1 h   | `{nick: {score, connected, last_seen}}`                        |
| `room:{code}:round`   | HASH | 1 h   | active plane & state                                           |
| `airport:list`        | JSON | ∞     | Pre‑cached airport directory                                   |
| `enrich_cache:{hex}`  | JSON | 24 h  | Cached Callsign, Country, Category from OpenSky                |
| `aeroapi_route:{hex}` | JSON | 6 h   | Cached Origin/Destination ICAO codes from AeroAPI              |

### 5.4 Resilience & Error Handling

- Ping every 10 s; drop WS after 3 missed pongs.
- Client reconnect back‑off 0.5 → 4 s with jitter; queues unsent commands.
- Gracefully display "Reconnecting …" banner; gameplay pauses if host offline.

---

## 6 Non‑Functional Requirements

- **Latency** ≤ 300 ms end‑to‑end map update.
- **Scale** ≤ 10 players room / 5 rooms concurrently.
- **Security** – anonymous, room code + nickname only; no cross‑room data leak.
- **Logging** – JSON lines, rotated weekly (20 MiB, gzip, 7 copies).
- **Accessibility** – colour‑blind safe palette; proper ARIA labels.
- **Internationalisation** – ASCII nicknames only for v1.

---

## 7 Technical Architecture & Configuration

```text
┌───────────┐  WS  ┌────────────┐  loopback  ┌────────────┐
│ React SPA │◀───▶│ FastAPI app│◀──────────▶│ dump1090   │
└───────────┘     └────────────┘             └────────────┘
      ▲                │ REST                        ▲
      │  Redis pub/sub ▼                            │ HTTP
 Browser          Redis server               OpenSky REST
```

### 7.1 `.env` variables

| Var                                     | Example                                              | Description                                    |
| --------------------------------------- | ---------------------------------------------------- | ---------------------------------------------- |
| `CENTER_LAT`                            | `42.378`                                             | Map default center                             |
| `CENTER_LON`                            | `-71.027`                                            | –                                              |
| `OPENSKY_USERNAME` / `OPENSKY_PASSWORD` | –                                                    | Enrichment API creds                           |
| `OSM_TILE_URL`                          | `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png` | Tile template                                  |
| `REDIS_URL`                             | `redis://localhost:6379/0`                           | Cache                                          |
| `ADSB_HOST`                             | `localhost`                                          | Hostname/IP of ADS-B source                    |
| `ADSB_PORT`                             | `30003`                                              | TCP port of ADS-B source                       |
| `KALMAN_PROCESS_NOISE`                  | `0.5`                                                | Kalman filter process noise variance           |
| `KALMAN_MEASUREMENT_NOISE`              | `10.0`                                               | Kalman filter measurement noise variance       |
| `PLANE_TTL_SECONDS`                     | `300`                                                | Time-to-live for plane data in Redis (seconds) |
| `FAKE_ADSB`                             | `0`                                                  | Use sample data (1) or live feed (0)           |

---

## 8 Deployment & Operations

- Single `docker‑compose.yml` (backend API + Nginx for static React build).
- **CI** – GitHub Actions: lint → test → build multi‑arch image → SSH into Pi → `docker compose pull && up -d`.
- **Public access** – default Cloudflare Tunnel (`cloudflared tunnel run`); alternatives: Let's Encrypt + DDNS, or Tailscale Funnel (see README).
- **Log rotation** – `/etc/logrotate.d/plane‑game`: weekly, size 20 M, compress.

### 8.1 Map Tiles

OpenStreetMap's public tile servers are fair‑use. Counter‑measures:

1. `Leaflet.TileLayer.Cached` ➜ IndexedDB cache.
2. Cloudflare edge caching hides most hits.
3. If play volume >50 000 tiles month⁻¹, switch to MapTiler free tier or self‑host `tileserver‑gl` on the Pi.

---

## 9 Stretch Goals & Roadmap

- **v1.1** – AI hint button; tuning scoring curve; airline livery thumbnails.
- **v1.2** – Native iOS thin client using same WS API.
- **v1.3** – Multi‑airport support (auto‑detect nearest field).

---

## 10 Open Questions / Risks

- **OpenSky rate limits** – 100 req day⁻¹ unauthenticated; monitor usage and cache aggressively.
- **Kalman tuning** – may require real‑world tweak of process/measurement noise.
- **Map tile quotas** – addressed in §8.1.

---

_Task breakdown lives in a separate document (`Plane Guessing Game – Task List v1.0`)._

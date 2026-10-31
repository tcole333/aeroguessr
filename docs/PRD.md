# AeroGuessr – Product Requirements Document

### Version 1.0 · April 26 2025 · requirements reviewed October 2026

This document says what the game must do. How it does it lives in [architecture.md](architecture.md), and how it runs on the Pi lives in [deployment.md](deployment.md).

---

## 1 Overview & Goals

A casual, real‑time web game where players guess the **other end** of flights overhead at Boston Logan using live ADS‑B signals captured by a Raspberry Pi. One player (the **host**) opens a "room" that friends join on their phones via a four‑letter code—Jackbox‑style. Rounds last about 30 s so the game keeps pace with short‑range aircraft visibility. The game is played **only on phones, in portrait**: every player, the host included, uses their own phone, and there is no shared TV or big screen. The codebase should be modular, easy to extend to a native iOS client later.

**Success criteria**
• A host can run a 5‑round game with up to 10 players on a home‑bandwidth Pi without manual resets.
• >95 % of WebSocket reconnects complete within 3 s, restoring state.
• Average outbound payload per client ≤ 5 kB s⁻¹ at peak play.

---

## 2 Personas & Usage Scenarios

| Persona                       | Scenario                                                                                          | Primary Device |
| ----------------------------- | ------------------------------------------------------------------------------------------------- | -------------- |
| **Travis** (power user, host) | Hosts at a BBQ from an iPhone: picks flights, starts rounds, guesses, and sees each reveal there. | iPhone         |
| **Jess** (casual guest)       | Scans QR / types room code, plays a few rounds while chatting.                                    | iPhone         |
| **Solo traveller**            | Waiting at the gate in Logan, opens single‑player mode for 10 min.                                | Android phone  |

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
The join endpoint returns a unique solo room code for subsequent WebSocket connections.

### 3.3 Scoring

- **Exact mode** – 100 points for correct IATA/ICAO.
- **Distance mode** – `max(0, 100 − distance_km / 10)` (linear taper to zero at 1 000 km). The formula lives in its own module for easy tuning later.

---

## 4 User Experience & Visual Design

- **Phones only, portrait.**
  - Every screen is designed for a phone in portrait, the host controls and the round reveal included. Each player sees the reveal on their own phone; no screen is designed for a TV or a desktop.
  - Today the panel sits below the map on phones and beside it from 768 px.
  - Phase 3 replaces this with a map‑first layout: a full‑screen map, a top HUD, a bottom sheet for flights and guessing, and results revealed on the map. The visual direction is the evolved departure board (#176).
- Leaflet map with an OpenFreeMap vector basemap. Pinch / two‑finger drag pan works natively.
- Collapsible **Panel** with tabs: **Planes**, **Leaderboard**, **Settings**.
  • **Planes** – list of active flights (callsign, altitude). Selecting pans/zooms map, shows details (altitude, speed, model, airline, SVG icon).
  • **Leaderboard** – live score table; confetti on lead changes.
  • **Settings** – night‑mode toggle, leave room, host controls.
- Plane icons: minimalist SVG; trail rendered as fading polyline (opacity decays over 60 s).
- Airport input uses client‑side fuzzy search (`Fuse.js`) over `data/airports.json` (about 3K airports, about 136 kB gzipped) for typo‑tolerant autocomplete. The same file defines which airports score.

---

## 5 Functional Requirements

### 5.1 Flight ingest, enrichment & smoothing

- Read live ADS‑B (SBS‑1 over TCP 30003 from `dump1090‑mutability`), or a synthetic feed for development.
- Smooth positions with a Kalman filter, so that planes don't jitter or flip heading.
- Attach a route (origin and destination) by matching callsigns against the monitored airport's FlightAware AeroAPI boards.
  - AeroAPI is called only while someone is playing, under a hard daily and per‑minute budget (§10).
- Planes leave the map 60 s after their last position, unless they are in a live round.

Pipeline details are in [architecture.md](architecture.md#ingest-pipeline).

### 5.2 Backend API (FastAPI v0)

- **REST:** create a room, join a room, join solo, and health probes. There is no endpoint that reads or deletes a room. Room and round state reach clients only over the WebSocket (#151).
- **WebSocket:** one connection per player, carrying every game action and update.
- **The contract** is generated from the code: [`api_openapi.yaml`](api_openapi.yaml) and [`ws_schema.yaml`](ws_schema.yaml). Paths and the message flow are in [architecture.md](architecture.md#wire-contract).

**Answer secrecy.** One end of every playable route is a round's answer, so no server message
before `roundResult` names a route's airports (#156). Delta planes never carry `origin` or
`destination`, for any plane. Each carries `route_hint: {guess_direction, known_airport,
eligible}` instead: the end players would guess, the monitored airport's ICAO code, and whether
the server accepts the plane for a round. Overflights get an empty hint and show neither end.
`planeSelectedConfirm` names no airport, because the host and the solo player also guess.
`roundResult` (`results[].correct_code` plus the plane `hex`) is the only reveal.

Known limitations, left to the Phase 2 engine:

- A solo session, or a second room with a lone host, can select the plane of another room's
  live round and read its answer from its own immediate `roundResult`. The plane's `hex` is in
  `roundStart`, and solo needs no `startRound` (`selectPlane` then `guess`), so one extra tab
  reads the answer within a fraction of a second. #171 tracks a per-plane round lock.
- Callsign and operator are sent and allow lookups on external flight-tracking sites.

### 5.3 State

All shared state lives in Redis, and every key expires. The keys are listed in [architecture.md](architecture.md#redis-keys).

### 5.4 Resilience & Error Handling

- Ping every 10 s; drop WS after 3 missed pongs.
- Client reconnect back‑off 0.5 → 4 s with jitter; queues unsent commands.
- Gracefully display "Reconnecting …" banner; gameplay pauses if host offline.

---

## 6 Non‑Functional Requirements

- **Latency** ≤ 300 ms end‑to‑end map update.
- **Scale** ≤ 10 players room / 5 rooms concurrently.
- **Security** – anonymous, room code + nickname only; no cross‑room data leak.
- **Logging** – every log stays bounded on the Pi's SD card ([deployment.md](deployment.md#logs)).
- **Accessibility** – colour‑blind safe palette; proper ARIA labels.
- **Internationalisation** – ASCII nicknames only for v1.

---

## 7 Technical Architecture & Configuration

See [architecture.md](architecture.md), including its configuration notes. Every backend setting is listed in [`.env.example`](../.env.example).

---

## 8 Deployment & Operations

- **Host:** one Raspberry Pi, with its own ADS‑B receiver, runs the Docker Compose stack.
- **Deploys:** every merge to `main` deploys itself. The Pi pulls, builds, and retries a failed deploy.
- **Public access:** a Cloudflare Tunnel serves aeroguessr.com.
- **Map tiles:** OpenFreeMap (decided 2026‑10‑16). It needs no API key and has no quota, but it also has no SLA. Its attribution must stay visible.

Details are in [deployment.md](deployment.md).

---

## 9 Stretch Goals & Roadmap

- **v1.1** – AI hint button; tuning scoring curve; airline livery thumbnails.
- **v1.2** – Native iOS thin client using same WS API.
- **v1.3** – Multi‑airport support (auto‑detect nearest field).

---

## 10 Open Questions / Risks

- **AeroAPI cost** – $0.005 per result set; requests only while someone plays, capped per UTC day (default 25) and per minute (8).
- **Kalman tuning** – may require real‑world tweak of process/measurement noise.
- **Map tiles** – OpenFreeMap has no SLA; a self‑hosted OpenFreeMap is the fallback (`MAP_STYLE_URL`).

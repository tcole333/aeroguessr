---
name: plane-game-context
description: Project context for the Plane Guessing Game - a real-time multiplayer flight guessing game using live ADS-B data. Use when working on this codebase, implementing features, fixing bugs, or understanding the architecture.
---

# Plane Guessing Game Context

## What This Project Does

A casual, real-time web game where players guess the origin or destination of flights overhead using live ADS-B signals. Players join a shared "room" via a code (Jackbox-style), competing in timed rounds.

## Core User Flow

1. Host creates room → gets 4-letter code (e.g., "ABCD")
2. Players join via code, pick nickname
3. Host selects a visible plane on the map
4. Players guess origin (arrivals) or destination (departures)
5. Scoring: Exact match (100 pts) or Distance-based (linear decay)
6. Leaderboard updates, next round begins

## Tech Stack

| Layer | Technology | Key Patterns |
|-------|------------|--------------|
| Backend | FastAPI, Python 3.12 | Async, Pydantic models |
| State | Redis | HASH per plane/room, TTL-based expiry |
| Real-time | WebSockets | JSON messages, delta updates |
| Frontend | React 18, TypeScript | Zustand slices, Tailwind |
| Map | Leaflet | Mobile-first, touch gestures |
| Data | dump1090 ADS-B | SBS-1 format on port 30003 |
| Deploy | Docker on Raspberry Pi | ARM64, supervisord |

## Key Architectural Decisions

### WebSocket Message Flow
```
Browser ←→ FastAPI WebSocket ←→ Redis ←→ Ingest Process
                                    ↓
                              dump1090 (ADS-B)
```

### State Storage (Redis)
- `plane:{hex}` - Position, velocity, trail, enrichment data
- `room:{code}:meta` - Room settings, host, mode
- `room:{code}:players` - Player scores, connection status
- `room:{code}:round` - Current round state

### Data Enrichment
Two-tier system for flight data:
1. OpenSky API - Callsign, country, category
2. FlightAware - Origin/destination airports

## Mobile-First Design

Primary target is portrait mode on phones. Key constraints:
- Collapsible bottom panel (docks left on tablet+)
- Touch-friendly plane selection
- Minimal data usage (<5 kB/s per client)
- 95% WebSocket reconnects within 3 seconds

## File Locations

| What | Where |
|------|-------|
| API routes | `backend/routes/rooms.py` |
| WebSocket handlers | `backend/routes/rooms.py::websocket_endpoint` |
| Game logic | `backend/services/` |
| ADS-B ingest | `backend/ingest/main.py` |
| Kalman filter | `backend/ingest/smoother_enu.py` |
| Zustand store | `frontend/src/store/createRootStore.tsx` |
| Map components | `frontend/src/components/Map/` |
| Type definitions | `frontend/types/` (auto-generated) |

## Testing Strategy

- **Unit tests**: pytest (backend), Vitest (frontend)
- **Integration**: Docker-based with real Redis
- **Fixtures**: FakeRedis for backend unit tests
- **Schema validation**: Auto-generated types from OpenAPI/WS schemas

## Common Gotchas

1. **Redis key types**: Use HASH for planes/rooms, not strings
2. **WebSocket host validation**: Check Redis dynamically, not connection-scoped variables
3. **Schema regeneration**: Run `make openapi` and `make ws-schema` after API changes
4. **Docker on Pi**: Code is baked into image, not volume mounted - rebuild required
5. **ADS-B timing**: MSG,3 (position) often arrives before MSG,1 (callsign)

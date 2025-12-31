# Backend Development Guide

FastAPI backend for the Plane Guessing Game with WebSocket support, Redis state, and ADS-B data ingestion.

## Stack

- **Framework**: FastAPI with async/await
- **State**: Redis (planes, rooms, players)
- **Real-time**: WebSockets for game state
- **Data**: ADS-B ingest from dump1090

## Project Structure

```
backend/
├── app.py              # FastAPI app initialization
├── routes/
│   ├── rooms.py        # Room REST + WebSocket handlers
│   └── logging.py      # Frontend log endpoint
├── services/
│   ├── broadcast.py    # WebSocket broadcasting
│   ├── room_manager.py # Room state management
│   └── scoring.py      # Distance/exact scoring
├── schemas/
│   └── *.py            # Pydantic models
├── ingest/
│   ├── main.py         # ADS-B ingest loop
│   ├── sbs_parser.py   # SBS-1 message parser
│   ├── smoother_enu.py # Kalman filter
│   ├── enrichment.py   # Flight data enrichment
│   └── enrichment_v2.py # V2 enrichment system
└── utils/
    ├── geo.py          # Geographic calculations
    └── airport_db.py   # Airport lookup
```

## Redis Schema

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `plane:{hex}` | HASH | 5 min | Position, velocity, trail, enrichment |
| `room:{code}:meta` | HASH | 1 hr | Mode, timeout, host, created_ts |
| `room:{code}:players` | HASH | 1 hr | `{nick: {score, connected}}` |
| `room:{code}:round` | HASH | 1 hr | Active round state |
| `enrich_cache:{hex}` | JSON | 24 hr | Cached enrichment data |

## WebSocket Message Types

**Client → Server:**
- `ping` - Heartbeat
- `guess` - Player guess submission
- `selectPlane` - Host plane selection
- `startRound` - Host starts round
- `leave` - Player leaving

**Server → Client:**
- `stateSync` - Full room state on connect
- `delta` - Incremental plane/score updates
- `roundStart` - Round begins
- `roundResult` - Round ends with scores
- `playerJoined`/`playerLeft` - Roster changes

## Key Patterns

### Async Everywhere
```python
async def my_handler(request: Request):
    data = await redis.hgetall(f"plane:{hex}")
    return JSONResponse(data)
```

### Pydantic Models
```python
class PlaneState(BaseModel):
    hex_ident: str
    lat: float
    lon: float
    alt: float
    # ... see schemas/plane.py
```

### WebSocket Handlers
All WebSocket message handlers are in `routes/rooms.py::websocket_endpoint`.
Use `_check_is_host()` for dynamic host validation.

### Ingest Pipeline
```
SBS-1 TCP → Parser → Kalman Filter → Redis
                  ↓
            Enrichment (OpenSky + FlightAware)
```

## Testing

```bash
# Unit tests
poetry run pytest tests/backend -m "not integration"

# Specific test
poetry run pytest tests/backend/test_scoring.py -v

# With coverage
poetry run pytest tests/backend --cov=backend
```

## Common Tasks

```bash
# Run backend only
poetry run uvicorn backend.app:app --reload --port 8000

# Run ingest with fake data
FAKE_ADSB=1 poetry run python -m backend.ingest.main

# Regenerate OpenAPI
make openapi

# Regenerate WebSocket schema
make ws-schema
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `FAKE_ADSB` | `0` | Use synthetic data |
| `ADSB_HOST` | `localhost` | dump1090 host |
| `ADSB_PORT` | `30003` | dump1090 port |
| `CENTER_LAT/LON` | Boston | Map center |
| `ENRICHMENT_V2_ENABLED` | `true` | Use V2 enrichment |

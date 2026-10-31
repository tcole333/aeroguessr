# Backend

[docs/architecture.md](../docs/architecture.md) covers the module layout, the game engine, the ingest pipeline and the Redis key table. Every setting is defined in `settings.py`, read with `get_settings()`, and listed in `.env.example`.

- **WebSocket handling** is all in `routes/rooms.py::websocket_endpoint`.
  - Host-only messages check the host in Redis with `_check_is_host`. Use it rather than caching host state.
- **Plane data for clients goes out as `PublicPlaneState`.**
  - Add a field to `PublicPlaneState` (`schemas/plane.py`) only if it cannot reveal a route's airports before `roundResult`. `PlaneState`, in the same file, is server-side only and holds the route.
  - `services/plane_visibility.py` builds the outgoing model.
- **Every Redis key has a TTL.** A write that can create a key sets the TTL atomically, and a read-modify-write runs under WATCH so it cannot recreate a deleted key ([architecture.md](../docs/architecture.md#redis-keys)). Add new keys to the table there.
- **AeroAPI:**
  - `ingest/aeroapi_client.py` makes the requests, and `ingest/board_refresher.py` is its only caller.
  - Every request reserves its pages in `ingest/aeroapi_budget.py` first. Redis errors deny the request.
  - `handle_message` makes no network calls.
- **After changing `schemas/ws.py` or a route,** run `make ws-schema` / `make openapi`, then `npm run gen:schema` in `frontend/`.
- **Tests mirror this tree under `tests/backend/`.** Run the unit suite from `tests/` (see [tests/README.md](../tests/README.md)).

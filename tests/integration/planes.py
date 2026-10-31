"""Seed planes into the backend's Redis for integration tests.

The backend's broadcast loop deletes ``plane:*`` keys that are outside the antenna range (250 km
around Boston Logan by default) or have not been updated for a minute, unless a round has
selected them. A seeded plane must therefore sit near Logan with a fresh timestamp, or it can
vanish between seeding and selection.
"""

import time

import redis.asyncio as redis

from backend.schemas.plane import PlaneState

LOGAN_LAT = 42.3656
LOGAN_LON = -71.0096
SEEDED_PLANE_TTL_SECONDS = 60


async def seed_plane(
    redis_conn: redis.Redis,
    hex_ident: str,
    *,
    origin: str | None,
    destination: str | None,
) -> PlaneState:
    """Store a plane over Logan flying ``origin`` -> ``destination`` and return it."""
    plane = PlaneState(
        hex_ident=hex_ident,
        lat=LOGAN_LAT,
        lon=LOGAN_LON,
        alt=10000,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=time.time(),
        origin=origin,
        destination=destination,
    )
    await redis_conn.set(f"plane:{hex_ident}", plane.model_dump_json(), ex=SEEDED_PLANE_TTL_SECONDS)
    return plane

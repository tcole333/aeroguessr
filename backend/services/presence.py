"""Redis-backed presence and gameplay-activity signals.

The ingest process and the API process run as separate OS processes (see
``supervisord.conf``) and share state only through Redis. The API process owns
the in-memory ``ConnectionManager`` and therefore knows how many rooms have
connected players; it publishes that count here. It also records when a player
last did something that counts as playing (create/join a room, select a plane,
start/skip a round, guess). The ingest process reads both to decide whether to
spend money on FlightAware AeroAPI board refreshes.
"""

import logging
import math
import time
from dataclasses import dataclass

from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# Redis key holding the current number of rooms with at least one connected player.
ACTIVE_ROOMS_KEY = "presence:active_rooms"

# TTL must comfortably exceed the broadcast heartbeat interval (~1s) so the key
# only disappears when the publishing (API) process has actually stopped. 10s
# tolerates a few missed heartbeats while still self-healing within seconds if
# the API process dies.
PRESENCE_TTL_SECONDS = 10

# Redis key holding the epoch seconds of the most recent gameplay action.
LAST_ACTIVITY_KEY = "presence:last_activity_ts"
# Far longer than any idle cutoff, so the key only matters while it is fresh.
ACTIVITY_TTL_SECONDS = 86400


async def publish_active_rooms(redis_client: RedisClient, count: int) -> None:
    """Publish the current active-room count with a self-expiring TTL.

    Called every heartbeat by the API process's broadcast loop. The TTL means
    that if the API process stops, the signal expires and consumers fall back to
    "no active rooms" automatically — no explicit cleanup required.
    """
    try:
        await redis_client.set(ACTIVE_ROOMS_KEY, str(count), expire_seconds=PRESENCE_TTL_SECONDS)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Failed to publish active-room presence: {e}")


async def record_gameplay_activity(redis_client: RedisClient, now: float | None = None) -> None:
    """Record that a player just did something that counts as playing.

    Errors are logged and swallowed: recording activity must never break gameplay.
    """
    timestamp = time.time() if now is None else now
    try:
        await redis_client.set(
            LAST_ACTIVITY_KEY, repr(timestamp), expire_seconds=ACTIVITY_TTL_SECONDS
        )
    except Exception as e:
        logger.warning(f"Failed to record gameplay activity: {e}")


@dataclass(frozen=True)
class PresenceSnapshot:
    """What the API process last published about players."""

    active_rooms: int
    last_activity_ts: float | None


def _parse_number(raw: object) -> float | None:
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


async def read_presence(redis_client: RedisClient) -> PresenceSnapshot:
    """Read the presence signals. Redis errors propagate so callers can fail closed.

    A missing or unparseable active-room count reads as 0; a missing or
    unparseable activity timestamp reads as None.
    """
    rooms = _parse_number(await redis_client.get(ACTIVE_ROOMS_KEY))
    last_activity = _parse_number(await redis_client.get(LAST_ACTIVITY_KEY))
    return PresenceSnapshot(
        active_rooms=int(rooms) if rooms is not None and rooms > 0 else 0,
        last_activity_ts=last_activity,
    )

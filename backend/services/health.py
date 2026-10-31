"""Readiness evaluation behind GET /readyz.

Ready means Redis answers and the ingest process has sent a fresh heartbeat while
connected to its ADS-B feed. The number of planes plays no part: a quiet sky is a
normal, ready state.
"""

import asyncio
import logging
import time
from typing import Optional

from backend.schemas.health import IngestCheck, ReadinessChecks, ReadinessResponse, RedisCheck
from backend.services.ingest_heartbeat import IngestHeartbeat, read_heartbeat
from backend.settings import get_settings
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# Maximum heartbeat age before ingest counts as stale. Ingest beats every 5s.
INGEST_HEALTH_THRESHOLD_SECONDS = get_settings().ingest_health_threshold_seconds

# Redis checks must finish well inside the callers' 5s timeouts (nginx, deploy
# gate), so a hung Redis yields a 503 rather than a hung probe.
READINESS_REDIS_TIMEOUT_SECONDS = 2.0

# API and ingest share one host clock. A heartbeat dated further ahead than this
# means the clock was stepped back (the Pi has no RTC), so it proves nothing.
HEARTBEAT_CLOCK_SKEW_TOLERANCE_SECONDS = 5.0

# Redis persists across container restarts, so a heartbeat written before this
# API process started belongs to a previous run and says nothing about the
# current ingest.
PROCESS_STARTED_TS = time.time()


async def check_readiness(redis_client: RedisClient) -> ReadinessResponse:
    """Check Redis and the ingest heartbeat. Never raises."""
    try:
        heartbeat = await asyncio.wait_for(
            _ping_and_read_heartbeat(redis_client), timeout=READINESS_REDIS_TIMEOUT_SECONDS
        )
    except TimeoutError:
        logger.warning(
            "Readiness: Redis did not answer within %ss", READINESS_REDIS_TIMEOUT_SECONDS
        )
        return _not_ready(
            "down", "unknown", f"Redis did not answer within {READINESS_REDIS_TIMEOUT_SECONDS:g}s"
        )
    except Exception as e:
        # Also covers non-connectivity errors such as WRONGTYPE on the heartbeat
        # key; the logged type tells them apart. Exception text stays out of the
        # response because /readyz is publicly reachable.
        logger.warning("Readiness: Redis check failed: %s", type(e).__name__)
        return _not_ready("down", "unknown", "Redis is unreachable")

    return _evaluate_ingest(heartbeat, now=time.time())


async def _ping_and_read_heartbeat(redis_client: RedisClient) -> Optional[IngestHeartbeat]:
    await redis_client.ping()
    return await read_heartbeat(redis_client)


def _evaluate_ingest(heartbeat: Optional[IngestHeartbeat], now: float) -> ReadinessResponse:
    if heartbeat is None:
        return _not_ready("ok", "down", "No ingest heartbeat in Redis; is ingest running?")

    age_seconds = now - heartbeat.ts
    age = round(age_seconds, 1)
    if heartbeat.ts < PROCESS_STARTED_TS:
        return _not_ready("ok", "down", "No ingest heartbeat since the API started", age)
    if heartbeat.ts > now + HEARTBEAT_CLOCK_SKEW_TOLERANCE_SECONDS:
        return _not_ready(
            "ok", "down", "Ingest heartbeat is dated in the future; the clock changed", age
        )
    if age_seconds > INGEST_HEALTH_THRESHOLD_SECONDS:
        return _not_ready(
            "ok",
            "stale",
            f"Last ingest heartbeat was {age:g}s ago (limit {INGEST_HEALTH_THRESHOLD_SECONDS:g}s)",
            age,
        )
    if not heartbeat.feed_connected:
        return _not_ready(
            "ok", "feed_disconnected", "Ingest is not connected to the ADS-B feed", age
        )

    return ReadinessResponse(
        status="ready",
        checks=ReadinessChecks(redis="ok", ingest="ok"),
        ingest_heartbeat_age_seconds=age,
    )


def _not_ready(
    redis: RedisCheck, ingest: IngestCheck, reason: str, age: Optional[float] = None
) -> ReadinessResponse:
    return ReadinessResponse(
        status="not_ready",
        checks=ReadinessChecks(redis=redis, ingest=ingest),
        reason=reason,
        ingest_heartbeat_age_seconds=age,
    )

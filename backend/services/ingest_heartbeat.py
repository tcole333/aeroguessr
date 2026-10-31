"""Redis heartbeat from the ingest process, read by the API's readiness probe.

The ingest process and the API process run as separate OS processes (see
``supervisord.conf``) and share state only through Redis, the same arrangement
as ``presence.py`` in the opposite direction. Ingest publishes a small JSON
heartbeat on a fixed cadence; ``/readyz`` reads it to decide whether ingest is
alive and connected to its ADS-B feed.

Plane keys cannot carry this signal: a quiet sky legitimately has no planes, and
the API's PlaneFilter deletes planes that stop updating, so "no planes" cannot
tell a dead ingest from an empty sky.

``feed_connected`` reflects the TCP connection to the feed only. A half-open
socket keeps it true until the read fails.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field

from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

INGEST_HEARTBEAT_KEY = "ingest:heartbeat"
INGEST_HEARTBEAT_INTERVAL_SECONDS = 5.0
# Readiness judges freshness from ``ts``, not from whether the key exists, so the
# TTL only needs to clean up after an ingest that is gone for good. Keeping it
# well above the readiness threshold lets /readyz report "stale" for a while
# before the key disappears.
INGEST_HEARTBEAT_TTL_SECONDS = 300


class IngestHeartbeat(BaseModel):
    """Payload stored at ``INGEST_HEARTBEAT_KEY``."""

    ts: float = Field(..., description="Unix time at which ingest wrote this heartbeat.")
    feed_connected: bool = Field(
        ..., description="Whether ingest currently holds a connection to the ADS-B feed."
    )


@dataclass
class FeedStatus:
    """Feed connection state that the ingest loop updates and the heartbeat reports."""

    connected: bool = False


async def publish_heartbeat(redis_client: RedisClient, feed_status: FeedStatus) -> None:
    """Write one heartbeat. Errors are logged and swallowed so ingest keeps running."""
    heartbeat = IngestHeartbeat(ts=time.time(), feed_connected=feed_status.connected)
    try:
        await redis_client.set(
            INGEST_HEARTBEAT_KEY,
            heartbeat.model_dump_json(),
            expire_seconds=INGEST_HEARTBEAT_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning(f"Failed to publish ingest heartbeat: {e}")


async def read_heartbeat(redis_client: RedisClient) -> Optional[IngestHeartbeat]:
    """Return the latest heartbeat, or None when it is missing or unreadable.

    Redis errors propagate so the caller can report Redis itself as down.
    """
    raw = await redis_client.get(INGEST_HEARTBEAT_KEY)
    if raw is None:
        return None
    try:
        return IngestHeartbeat.model_validate_json(raw)
    except ValueError:
        logger.warning("Ignoring unreadable ingest heartbeat")
        return None


async def _publish_forever(redis_client: RedisClient, feed_status: FeedStatus) -> None:
    while True:
        await publish_heartbeat(redis_client, feed_status)
        await asyncio.sleep(INGEST_HEARTBEAT_INTERVAL_SECONDS)


def start_heartbeat(redis_client: RedisClient) -> FeedStatus:
    """Publish heartbeats until the calling task finishes.

    Returns the ``FeedStatus`` the caller updates as its feed connects and drops.
    The heartbeat task is cancelled when the calling task ends for any reason
    (return, exception or cancellation), so heartbeats stop with ingest and the
    last one goes stale.
    """
    owner = asyncio.current_task()
    if owner is None:
        raise RuntimeError("start_heartbeat must be called from within an asyncio task")

    feed_status = FeedStatus()
    heartbeat_task = asyncio.create_task(
        _publish_forever(redis_client, feed_status), name="ingest-heartbeat"
    )
    owner.add_done_callback(lambda _: heartbeat_task.cancel())
    return feed_status

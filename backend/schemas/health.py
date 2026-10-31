"""Response models for the liveness (/healthz) and readiness (/readyz) probes."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

RedisCheck = Literal["ok", "down"]
IngestCheck = Literal["ok", "down", "stale", "feed_disconnected", "unknown"]


class LivenessResponse(BaseModel):
    """The API process is up and serving requests."""

    status: Literal["ok"] = "ok"
    version: str = Field(
        ..., description="The version this install runs, as in GET /api/v0/config."
    )


class ReadinessChecks(BaseModel):
    redis: RedisCheck = Field(..., description="Whether Redis answered within the time limit.")
    ingest: IngestCheck = Field(
        ...,
        description=(
            "ok: fresh heartbeat with the ADS-B feed connected. down: no usable heartbeat "
            "from the current ingest run. stale: heartbeat older than the threshold. "
            "feed_disconnected: ingest is alive but not connected to its feed. "
            "unknown: Redis is down, so ingest could not be checked."
        ),
    )


class ReadinessResponse(BaseModel):
    """Whether the service can run games: Redis is up and ingest is on its feed."""

    status: Literal["ready", "not_ready"]
    checks: ReadinessChecks
    reason: Optional[str] = Field(
        None, description="Why the service is not ready; null when ready."
    )
    ingest_heartbeat_age_seconds: Optional[float] = Field(
        None, description="Age of the latest ingest heartbeat, when there is one."
    )

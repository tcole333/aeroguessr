"""Liveness and readiness probes."""

from fastapi import APIRouter, Depends, Response, status

from backend.routes.rooms import get_redis
from backend.schemas.health import LivenessResponse, ReadinessResponse
from backend.services.health import check_readiness
from backend.settings import get_settings
from backend.utils.redis_async import RedisClient
from backend.version import app_version

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Liveness probe: the API process is up and serving requests. Names the version too.

    Does no I/O on purpose, so it fails only when this process is broken. The
    Docker healthcheck uses it; dependency checks belong to /readyz. The version
    is worked out at startup.
    """
    return LivenessResponse(version=app_version(get_settings()))


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Not ready; `checks` and `reason` say why",
        }
    },
)
async def readiness(
    response: Response, redis: RedisClient = Depends(get_redis)
) -> ReadinessResponse:
    """Readiness probe: Redis is up and ingest is heartbeating on its ADS-B feed.

    Returns 503 when not ready. The deploy gate (scripts/auto-update.sh) uses this.
    An empty sky is ready: plane counts are not part of the check.
    """
    result = await check_readiness(redis)
    if result.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result

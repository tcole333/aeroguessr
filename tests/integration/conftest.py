"""Fixtures for integration tests that drive a live backend over HTTP and WebSockets.

The backend under test must be started separately with ``REDIS_URL`` set to the same database
as ``TEST_REDIS_URL``, so tests can seed planes and inspect room state through ``real_redis``.
See tests/README.md for the native and docker-compose recipes.
"""

import os
import time
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis

INTEGRATION_BASE_URL_ENV = "INTEGRATION_BASE_URL"
BACKEND_READY_TIMEOUT_SECONDS = 30.0


@pytest.fixture(scope="session")
def integration_base_url() -> str:
    """``INTEGRATION_BASE_URL``, once the backend there answers ``/healthz``.

    Readiness means "the server answers HTTP"; the health status code is ignored so this does
    not depend on how the endpoint reports its dependencies. The wait runs once per session,
    and pytest re-raises a failed wait for every later test instead of waiting again.
    """
    base_url = os.environ.get(INTEGRATION_BASE_URL_ENV)
    if not base_url:
        pytest.fail(
            f"{INTEGRATION_BASE_URL_ENV} is not set. Point it at the running backend under test, "
            "e.g. http://127.0.0.1:8000. See tests/README.md.",
            pytrace=False,
        )
    base_url = base_url.rstrip("/")

    deadline = time.monotonic() + BACKEND_READY_TIMEOUT_SECONDS
    last_error: Exception | None = None
    with httpx.Client(base_url=base_url, timeout=1.0) as probe:
        while time.monotonic() < deadline:
            try:
                probe.get("/healthz")
                return base_url
            except httpx.RequestError as exc:
                last_error = exc
                time.sleep(0.5)
    pytest.fail(
        f"Backend at {base_url} did not answer /healthz within "
        f"{BACKEND_READY_TIMEOUT_SECONDS:.0f}s. Last error: {last_error!r}",
        pytrace=False,
    )


@pytest_asyncio.fixture
async def integration_client(
    integration_base_url: str, real_redis: redis.Redis
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An ``httpx.AsyncClient`` bound to the live backend.

    It depends on ``real_redis`` so every live-backend test starts and ends on a flushed
    database, including tests that never touch Redis directly.
    """
    async with httpx.AsyncClient(base_url=integration_base_url) as client:
        yield client

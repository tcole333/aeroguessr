"""Fixtures for route tests that run on FakeRedis and, under ``-m integration``, real Redis."""

from typing import Iterator

import pytest

from backend.app import app
from backend.routes.rooms import get_redis
from backend.utils.redis_async import RedisClient


@pytest.fixture(autouse=True)
def _redis_outlives_the_app(request: pytest.FixtureRequest) -> None:
    """Set up a test's ``game_redis`` before its ``test_client``, so Redis is torn down last.

    A backstop for tests that start a handler through ``test_client``, such as a raw
    ``aconnect_ws``. ``game_socket`` waits for its own handler and remains the way to open a
    socket. Fixtures are torn down in reverse order of setup, and autouse fixtures are set up
    first. Requesting ``game_redis`` here therefore closes ``test_client``, which waits for the
    last socket opened on it, before Redis is flushed and its pool disconnected. A handler cut
    off mid-command can otherwise hang the test (see ``game_socket``).
    """
    if "game_redis" in request.fixturenames:
        request.getfixturevalue("game_redis")


@pytest.fixture(params=["fakeredis", pytest.param("real-redis", marks=pytest.mark.integration)])
def game_redis(request: pytest.FixtureRequest) -> Iterator[RedisClient]:
    """Serve the app from a fresh Redis: FakeRedis, or the db named by TEST_REDIS_URL.

    Both stores come from the shared fixtures (``redis_client`` in tests/backend/conftest.py,
    ``real_redis_client`` in tests/conftest.py), which flush them around each test. This
    fixture is sync so it can request only the one its param needs.
    """
    fixture_name = "real_redis_client" if request.param == "real-redis" else "redis_client"
    client: RedisClient = request.getfixturevalue(fixture_name)

    async def override_get_redis() -> RedisClient:
        return client

    app.dependency_overrides[get_redis] = override_get_redis
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_redis, None)

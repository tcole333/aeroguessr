"""Fixtures shared by every test tree.

``real_redis`` is the single entry point for tests that need a real Redis server. It follows
the real-Redis test contract documented in ``tests/README.md``:

* the database comes from ``TEST_REDIS_URL`` and the test fails (never skips) when it is unset;
* database 0 is refused, because that is where dev stacks keep live game state;
* the fixture flushes only that one database, before and after each test.
"""

import os
from typing import AsyncGenerator, Iterator

# Tests never read a developer's .env, which may hold a real AeroAPI key. This must run
# before any backend module reads its settings.
os.environ["AEROGUESSR_ENV_FILE"] = ""

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
import redis.asyncio as redis  # noqa: E402
from redis.connection import parse_url  # noqa: E402

from backend.settings import get_settings  # noqa: E402
from backend.utils.redis_async import RedisClient  # noqa: E402

TEST_REDIS_URL_ENV = "TEST_REDIS_URL"


@pytest.fixture(autouse=True)
def fresh_settings() -> Iterator[None]:
    """Re-read settings in every test, so ``monkeypatch.setenv`` before the first read applies."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def dedicated_test_redis_url() -> str:
    """Return ``TEST_REDIS_URL``, failing the test when it is unset or points at db 0."""
    url = os.environ.get(TEST_REDIS_URL_ENV)
    if not url:
        pytest.fail(
            f"{TEST_REDIS_URL_ENV} is not set. Real-Redis tests flush their database, so they "
            "need a dedicated one, e.g. redis://127.0.0.1:6379/1. See tests/README.md.",
            pytrace=False,
        )
    if int(parse_url(url).get("db", 0)) == 0:
        pytest.fail(
            f"{TEST_REDIS_URL_ENV}={url} selects db 0. Real-Redis tests flush their database, "
            "so point them at a dedicated non-zero db.",
            pytrace=False,
        )
    return url


@pytest_asyncio.fixture
async def real_redis() -> AsyncGenerator[redis.Redis, None]:
    """A decoded ``redis.asyncio.Redis`` on the dedicated test database, flushed around the test."""
    client = redis.Redis.from_url(dedicated_test_redis_url(), decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest_asyncio.fixture
async def real_redis_client(
    real_redis: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[RedisClient, None]:
    """The application's ``RedisClient`` on the dedicated test database, configured as in prod.

    It is built from ``REDIS_URL`` rather than wrapping ``real_redis``: production hands out a
    fresh connection object per call on a shared pool, and wrapping one client would let one
    call's ``async with`` close the pool under concurrent callers.
    """
    monkeypatch.setenv("REDIS_URL", dedicated_test_redis_url())
    get_settings.cache_clear()
    client = RedisClient()
    yield client
    connection = await client.get_connection()
    await connection.aclose(close_connection_pool=True)

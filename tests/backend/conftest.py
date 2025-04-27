import asyncio
import logging
from typing import AsyncGenerator

import fakeredis.aioredis
import pytest_asyncio

# Use AsyncClient and ASGITransport
from httpx import AsyncClient
from httpx_ws.transport import ASGIWebSocketTransport

# Import the FastAPI app instance
from backend.app import app
from backend.routes.rooms import get_redis_client  # Import the dependency getter
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

# --- Function-Scoped Fake Redis Instance --- #


@pytest_asyncio.fixture(scope="function")
async def fake_redis_instance() -> AsyncGenerator[fakeredis.aioredis.FakeRedis, None]:
    """Provides a fresh FakeRedis instance for each test function."""
    loop_id = id(asyncio.get_running_loop())
    logger.info(f"[Fixture fake_redis_instance] Creating FakeRedis. Loop ID: {loop_id}")
    instance = fakeredis.aioredis.FakeRedis()
    yield instance
    # Clean up the instance after the test
    logger.info(f"[Fixture fake_redis_instance] Closing FakeRedis. Loop ID: {loop_id}")
    await instance.aclose()


# --- Function-Scoped Fixture to Override Dependency and Provide Client --- #


@pytest_asyncio.fixture(scope="function")
async def redis_client(
    fake_redis_instance: fakeredis.aioredis.FakeRedis,
) -> AsyncGenerator[RedisClient, None]:
    """
    Overrides the Redis dependency for a single test function using the
    provided fake_redis_instance, clears it, and provides the wrapped client.
    """
    loop_id = id(asyncio.get_running_loop())
    logger.info(
        f"[Fixture redis_client] START. Loop ID: {loop_id}, FakeRedis ID: {id(fake_redis_instance)}"
    )
    # Create the client wrapper using the test-specific fake instance
    client_wrapper = RedisClient()
    client_wrapper.redis = fake_redis_instance

    # Define the override function for this specific test
    async def override_get_redis_for_test() -> RedisClient:
        logger.info(
            f"[Dependency Override] get_redis_client called. Returning client wrapping "
            f"FakeRedis ID: {id(client_wrapper.redis)}. Loop ID: {id(asyncio.get_running_loop())}"
        )
        return client_wrapper

    # Apply the override
    logger.info(f"[Fixture redis_client] Applying override. Loop ID: {loop_id}")
    original_override = app.dependency_overrides.get(get_redis_client)
    app.dependency_overrides[get_redis_client] = override_get_redis_for_test

    try:
        # Clear redis before the test runs
        logger.info(
            f"[Fixture redis_client] Flushing FakeRedis ID: {id(fake_redis_instance)}. "
            f"Loop ID: {loop_id}"
        )
        await fake_redis_instance.flushall()
        # Yield the wrapped client to the test
        logger.info(f"[Fixture redis_client] Yielding client wrapper. Loop ID: {loop_id}")
        yield client_wrapper
    finally:
        # Restore the original override (or remove) after the test
        logger.info(f"[Fixture redis_client] Restoring override. Loop ID: {loop_id}")
        if original_override:
            app.dependency_overrides[get_redis_client] = original_override
        else:
            if get_redis_client in app.dependency_overrides:
                del app.dependency_overrides[get_redis_client]
        logger.info(f"[Fixture redis_client] END. Loop ID: {loop_id}")


# --- Test Client Fixture (Async) --- #


@pytest_asyncio.fixture(scope="function")
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Provides an asynchronous test client (httpx.AsyncClient).
    The app it uses will have dependencies overridden by the redis_client fixture.
    """
    loop_id = id(asyncio.get_running_loop())
    logger.info(f"[Fixture test_client] Creating AsyncClient. Loop ID: {loop_id}")
    # The redis_client fixture applies the override before this client is used
    client = AsyncClient(transport=ASGIWebSocketTransport(app=app), base_url="http://testserver")
    logger.info(f"[Fixture test_client] Yielding AsyncClient ID: {id(client)}. Loop ID: {loop_id}")
    try:
        yield client
    finally:
        logger.info(
            f"[Fixture test_client] Closing AsyncClient ID: {id(client)}. Loop ID: {loop_id}"
        )
        try:
            await client.aclose()
        except RuntimeError as e:
            logger.warning(f"Error closing AsyncClient: {e}")


# Remove AsyncClient fixture definition
# @pytest_asyncio.fixture(scope="function")
# async def test_client() -> AsyncGenerator[AsyncClient, None]:
#    ...

# Remove old override logic at module level
# app.dependency_overrides[RedisClient] = override_get_redis_client

# Remove old test_client fixture
# @pytest_asyncio.fixture(scope="session")
# async def test_client() -> AsyncGenerator[AsyncClient, None]:
#    """
#    Provides an asynchronous test client for making requests to the FastAPI app.
#    Uses ASGITransport to interact with the app directly without a running server.
#    """
#    # Use ASGITransport to wrap the app
#    async with AsyncClient(transport=ASGITransport(app=app),
#       base_url="http://testserver") as client:
#        yield client

# Remove old redis_client fixture definition if it was conflicting

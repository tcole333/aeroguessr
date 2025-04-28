import asyncio
import logging
import time
from typing import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis

# Remove TestClient import
# from fastapi.testclient import TestClient

# Remove app import, not needed for httpx client against running server
# from backend.main import app

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture(scope="function")
async def integration_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Fixture providing an httpx.AsyncClient configured for the integration test server.

    Waits for the backend service to become healthy before yielding the client.
    The client base URL points to the backend service within the Docker network.
    """
    # Service name defined in docker-compose.test.yml
    service_name = "backend-test"
    port = 8000  # Assuming default port
    base_url = f"http://{service_name}:{port}"
    health_url = f"{base_url}/healthz"

    # Wait up to 30s for the service to be healthy
    wait_start = time.time()
    last_error = None
    while time.time() - wait_start < 30:
        try:
            async with httpx.AsyncClient() as client:  # Create temporary client for health check
                resp = await client.get(health_url, timeout=1.0)
                if resp.status_code == 200:
                    logger.info(f"\nIntegration service {base_url} is healthy.")
                    # Yield the properly configured client for tests
                    async with httpx.AsyncClient(base_url=base_url) as integration_test_client:
                        yield integration_test_client
                    return  # Exit generator successfully
                else:
                    last_error = f"Health check failed with status: {resp.status_code}"
                    logger.info(f". (Health status: {resp.status_code})", end="")

        except httpx.RequestError as e:
            last_error = f"Health check connection error: {e}"
            logger.info(". (Connection error)", end="")
        except Exception as e:
            last_error = f"Health check unexpected error: {e}"
            logger.info(f". (Error: {type(e).__name__})", end="")

        await asyncio.sleep(1)

    pytest.fail(
        f"Backend service at {base_url} did not become healthy after 30s. Last error: {last_error}",
        pytrace=False,
    )


@pytest_asyncio.fixture(scope="function")
async def integration_redis() -> AsyncGenerator[redis.Redis, None]:
    """Fixture providing an async Redis client connected to the integration test Redis."""
    # Service name from docker-compose.test.yml
    redis_host = "redis-test"
    redis_port = 6379
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    try:
        # Create a connection pool
        pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
        # Create the client instance
        client = redis.Redis(connection_pool=pool)

        # Check connection
        await client.ping()
        logger.info(f"\nConnected to integration Redis at {redis_url}")
        yield client

    except redis.RedisError as e:
        pytest.fail(f"Failed to connect to integration Redis at {redis_url}: {e}")
    finally:
        # Clean up the connection pool
        if "client" in locals() and client.connection_pool:
            await client.connection_pool.disconnect()
        logger.info(f"\nDisconnected from integration Redis at {redis_url}")

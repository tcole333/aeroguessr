import os
import time
from typing import AsyncGenerator

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(scope="session")
async def http_server() -> AsyncGenerator[TestClient, None]:
    """Fixture that provides a test client for the FastAPI app.

    Checks that the service is available before yielding the client.
    """
    url = os.environ.get("TEST_SERVER_URL", "http://localhost:8000")
    health_url = f"{url}/healthz"

    # Wait up to 30s for the service to be healthy
    for _ in range(30):
        try:
            resp = httpx.get(health_url, timeout=1.0)
            if resp.status_code == 200:
                async with TestClient(app) as client:
                    yield client
                return
        except Exception:
            time.sleep(1)

    pytest.skip(f"Backend service not available at {health_url}")

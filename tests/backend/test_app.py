"""Tests for main app endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_basic(test_client: AsyncClient) -> None:
    """Test health check returns expected structure."""
    response = await test_client.get("/healthz")
    assert response.status_code == 200
    data = response.json()

    # Check all required fields are present
    assert "status" in data
    assert "api" in data
    assert "redis" in data
    assert "ingest" in data

    # API should always be healthy if we got a response
    assert data["api"] == "healthy"

    # Status should be one of the valid values
    assert data["status"] in ["ok", "degraded", "unhealthy"]


@pytest.mark.asyncio
async def test_root_endpoint(test_client: AsyncClient) -> None:
    """Test root endpoint returns welcome message."""
    response = await test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "Plane Guessing Game" in data["message"]

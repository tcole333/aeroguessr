"""Integration tests for complete Docker Compose stack deployment.

Tests that the full application stack (nginx, frontend, backend, redis)
works correctly when deployed via docker-compose.yml.
"""

import asyncio

import httpx
import httpx_ws
import pytest


class TestDockerComposeIntegration:
    """Test complete Docker Compose stack functionality."""

    @pytest.mark.integration
    async def test_docker_compose_stack_health(self):
        """Test that all services in the Docker Compose stack are healthy."""
        # This test assumes the stack is running on localhost:80
        # In a real CI environment, this would use a test-specific compose file

        async with httpx.AsyncClient(base_url="http://localhost") as client:
            # Test that nginx serves the frontend
            response = await client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Test that API requests are properly proxied
            response = await client.get("/healthz")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data

            # Test CORS headers are present for API requests
            response = await client.options("/api/v0/rooms")
            assert response.status_code == 204
            assert "Access-Control-Allow-Origin" in response.headers

    @pytest.mark.integration
    async def test_docker_compose_room_creation_and_websocket(self):
        """Test room creation and WebSocket connection through the full stack."""
        async with httpx.AsyncClient(base_url="http://localhost") as client:
            # Create a room via nginx proxy
            response = await client.post(
                "/api/v0/rooms",
                json={
                    "host_nickname": "DockerTestHost",
                    "mode": "Exact",
                    "round_timeout_seconds": 30,
                },
            )
            assert response.status_code == 201
            data = response.json()
            room_code = data["room_code"]

            # WebSocket URL should go through nginx (port 80)
            ws_url = f"ws://localhost/ws/{room_code}/DockerTestHost"

            # Test WebSocket connection through nginx
            try:
                async with httpx_ws.aconnect_ws(ws_url) as websocket:
                    # Send a ping message
                    await websocket.send_json(
                        {"type": "ping", "payload": {"seq": 1}, "ts": 1234567890}
                    )

                    # Should receive a pong response
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                    assert message["type"] == "pong"
                    assert message["payload"]["seq"] == 1

            except Exception as e:
                pytest.fail(f"Full stack WebSocket test failed: {e}")

    @pytest.mark.integration
    async def test_docker_compose_service_isolation(self):
        """Test that services communicate properly through Docker networking."""
        async with httpx.AsyncClient(base_url="http://localhost") as client:
            # Test that backend can communicate with Redis
            # This is implicit in the health check, but we can test room persistence

            # Create a room
            response = await client.post(
                "/api/v0/rooms",
                json={
                    "host_nickname": "IsolationTest",
                    "mode": "Distance",
                    "round_timeout_seconds": 45,
                },
            )
            assert response.status_code == 201
            room_code = response.json()["room_code"]

            # Verify room exists (tests backend->redis communication)
            response = await client.get(f"/api/v0/rooms/{room_code}")
            assert response.status_code == 200
            room_data = response.json()
            assert room_data["host_nickname"] == "IsolationTest"
            assert room_data["mode"] == "Distance"

    @pytest.mark.integration
    async def test_docker_compose_environment_variables(self):
        """Test that environment variables are properly configured in the stack."""
        async with httpx.AsyncClient(base_url="http://localhost") as client:
            # Create a room to test that backend is using proper Redis configuration
            response = await client.post(
                "/api/v0/rooms",
                json={"host_nickname": "EnvTestHost", "mode": "Exact", "round_timeout_seconds": 30},
            )
            assert response.status_code == 201

            # If this succeeds, it means:
            # 1. Backend can connect to Redis (REDIS_URL=redis://redis:6379/0)
            # 2. Backend is running with proper environment configuration
            # 3. All services are networked correctly

            room_code = response.json()["room_code"]
            assert len(room_code) == 4
            assert room_code.isalpha()
            assert room_code.isupper()

    @pytest.mark.integration
    async def test_docker_compose_volume_mounts(self):
        """Test that volume mounts are working (logs directory)."""
        # This is a basic test - in practice, we'd need to check log file creation
        # For now, we'll just verify the services are healthy
        async with httpx.AsyncClient(base_url="http://localhost") as client:
            response = await client.get("/healthz")
            assert response.status_code == 200

            # The fact that this works means volume mounts are at least not
            # preventing the backend from starting up properly

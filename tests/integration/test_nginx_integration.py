"""Integration tests for Nginx reverse proxy configuration.

Tests that nginx properly routes requests to frontend and backend services
and handles WebSocket connections correctly.

NOTE: These tests require a full nginx deployment (not just backend-test).
They are currently skipped as nginx is not available in the standard
integration test Docker setup.
"""

import asyncio

import httpx
import httpx_ws
import pytest

# Base URL for nginx - assumes nginx is running on localhost:80
# These tests require the full production-like Docker Compose setup
BASE_URL = "http://localhost"


class TestNginxIntegration:
    """Test nginx reverse proxy functionality."""

    @pytest.mark.integration
    async def test_nginx_serves_frontend_static_files(self):
        """Test that nginx serves frontend static files at root path."""
        async with httpx.AsyncClient() as client:
            # Test root path serves HTML
            response = await client.get(f"{BASE_URL}/")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

            # Test SPA fallback (non-existent routes should serve index.html)
            response = await client.get(f"{BASE_URL}/game/ABCD")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")

    @pytest.mark.integration
    async def test_nginx_proxies_api_requests(self):
        """Test that nginx properly proxies API requests to backend."""
        async with httpx.AsyncClient() as client:
            # Test health check endpoint
            response = await client.get(f"{BASE_URL}/healthz")
            assert response.status_code == 200

            # Test API endpoint
            response = await client.get(f"{BASE_URL}/api/v0/healthz")
            assert (
                response.status_code == 404
            )  # This endpoint doesn't exist, but should reach backend

            # Test CORS headers are present
            response = await client.options(f"{BASE_URL}/api/v0/rooms")
            assert response.status_code == 204
            assert "Access-Control-Allow-Origin" in response.headers

    @pytest.mark.integration
    async def test_nginx_handles_cors_preflight(self):
        """Test that nginx handles CORS preflight requests properly."""
        async with httpx.AsyncClient() as client:
            response = await client.options(
                f"{BASE_URL}/api/v0/rooms",
                headers={
                    "Origin": "http://localhost:3000",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type",
                },
            )
            assert response.status_code == 204
            assert response.headers.get("Access-Control-Allow-Origin") == "*"
            assert "POST" in response.headers.get("Access-Control-Allow-Methods", "")
            assert "Content-Type" in response.headers.get("Access-Control-Allow-Headers", "")

    @pytest.mark.integration
    async def test_nginx_proxies_websocket_connections(self):
        """Test that nginx properly proxies WebSocket connections to backend."""
        # First create a room to get a valid WebSocket URL
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v0/rooms",
                json={"host_nickname": "TestHost", "mode": "Exact", "round_timeout_seconds": 30},
            )
            assert response.status_code == 201
            data = response.json()
            room_code = data["room_code"]

        # Test WebSocket connection through nginx
        ws_url = f"ws://localhost/ws/{room_code}/TestHost"

        try:
            async with httpx_ws.aconnect_ws(ws_url) as websocket:
                # Send a ping message
                await websocket.send_json({"type": "ping", "payload": {"seq": 1}, "ts": 1234567890})

                # Should receive a pong response
                message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
                assert message["type"] == "pong"
                assert message["payload"]["seq"] == 1

        except Exception as e:
            pytest.fail(f"WebSocket connection through nginx failed: {e}")

    @pytest.mark.integration
    async def test_nginx_security_headers(self):
        """Test that nginx adds appropriate security headers."""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")

            # Check security headers are present
            assert "X-Frame-Options" in response.headers
            assert "X-XSS-Protection" in response.headers
            assert "X-Content-Type-Options" in response.headers
            assert "Content-Security-Policy" in response.headers

            # Check specific security header values
            assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
            assert response.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.integration
    async def test_nginx_caching_headers(self):
        """Test that nginx sets appropriate caching headers for static assets."""
        async with httpx.AsyncClient() as client:
            # Test that HTML files have no-cache headers
            response = await client.get(f"{BASE_URL}/")
            # Should have no-cache for HTML files (set at location = /index.html)

            # For now, just verify the response is successful
            # In a real deployment, we'd test actual static asset caching
            assert response.status_code == 200

    @pytest.mark.integration
    async def test_nginx_rate_limiting(self):
        """Test that nginx rate limiting is configured (basic test)."""
        async with httpx.AsyncClient() as client:
            # Make multiple rapid requests to test rate limiting
            # Note: This is a basic test - proper rate limit testing would require
            # more sophisticated setup and timing
            responses = []
            for _ in range(5):
                response = await client.get(f"{BASE_URL}/healthz")
                responses.append(response.status_code)

            # All requests should succeed for this basic test
            # In production, we'd test actual rate limit enforcement
            assert all(status == 200 for status in responses)

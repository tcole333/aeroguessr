"""The game WebSocket of the in-process app, for route tests that also run on real Redis."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from httpx import AsyncClient
from httpx_ws import AsyncWebSocketSession, aconnect_ws
from httpx_ws.transport import ASGIWebSocketTransport

from backend.app import app
from backend.schemas.ws import WSMessage


@asynccontextmanager
async def game_socket(ws_path: str) -> AsyncIterator[AsyncWebSocketSession]:
    """Yield a game socket on a client of its own. Leaving the block waits for the server's handler.

    On exit it sends ``leave`` and closes its client, in the task that opened the socket.
    ``aconnect_ws`` returns without waiting for the server's handler; only closing the client
    waits for it. A handler still running when the fixtures close Redis can hang the test:
    asyncio in Python 3.12, 3.13.0-3.13.9 and 3.14.0 can lose a Redis connection closed under
    it and wait on the next one forever (gh-136234).
    """
    async with AsyncClient(
        transport=ASGIWebSocketTransport(app=app), base_url="http://testserver"
    ) as client:
        async with aconnect_ws(ws_path, client=client, keepalive_ping_interval_seconds=None) as ws:
            yield ws
            await ws.send_json(WSMessage(type="leave", payload={}).model_dump())

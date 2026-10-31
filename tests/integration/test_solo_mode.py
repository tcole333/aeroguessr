import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.schemas.ws import WSMessage

from .planes import seed_plane
from .ws_helpers import wait_for_message

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_solo_mode_flow(integration_client: AsyncClient, real_redis: redis.Redis) -> None:
    join_resp = await integration_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    assert join_resp.status_code == status.HTTP_200_OK
    ws_url = join_resp.json()["ws_url"]

    await seed_plane(real_redis, "abcd", origin="KBOS", destination="KJFK")

    async with aconnect_ws(ws_url, client=integration_client) as ws:
        await wait_for_message(ws, "stateSync")

        await ws.send_json(WSMessage(type="selectPlane", payload={"hex": "abcd"}).model_dump())
        await wait_for_message(ws, "planeSelectedConfirm")

        await ws.send_json(WSMessage(type="guess", payload={"airport_code": "KJFK"}).model_dump())
        result = await wait_for_message(ws, "roundResult")

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())

    assert result["payload"]["results"][0]["score_awarded"] == 100

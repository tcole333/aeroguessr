import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.ingest.main import PlaneState
from backend.schemas.ws import WSMessage, WSMessageType
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def test_solo_ws_flow(test_client: AsyncClient, redis_client: RedisClient) -> None:
    join_resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    data = join_resp.json()
    ws_path = data["ws_url"].replace("ws://testserver", "")

    plane = PlaneState(
        hex_ident="abcd",
        lat=0,
        lon=0,
        alt=0,
        lat_v=0,
        lon_v=0,
        alt_v=0,
        last_update_ts=0,
        origin="KBOS",
        destination="KJFK",
    )
    await redis_client.set_json("plane:abcd", plane)

    async with aconnect_ws(ws_path, client=test_client, keepalive_ping_interval_seconds=None) as ws:
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        select_msg = WSMessage(type="selectPlane", payload={"hex": "abcd"})
        await ws.send_json(select_msg.model_dump())
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM

        guess_msg = WSMessage(type="guess", payload={"airport_code": "KJFK"})
        await ws.send_json(guess_msg.model_dump())
        result = WSMessage(**await ws.receive_json())
        assert result.type == WSMessageType.ROUND_RESULT

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())

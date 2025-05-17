import httpx_ws._api
import pytest
import redis.asyncio as redis
from fastapi import status
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.ingest.main import PlaneState
from backend.schemas.ws import WSMessage, WSMessageType

pytestmark = pytest.mark.integration


httpx_ws._api.AsyncWebSocketSession._background_keepalive = lambda *a, **k: None


@pytest.mark.asyncio
async def test_solo_mode_flow(
    integration_client: AsyncClient, integration_redis: redis.Redis
) -> None:
    join_resp = await integration_client.post(
        "/api/v0/rooms/solo/join", json={"nickname": "Solo"}
    )
    assert join_resp.status_code == status.HTTP_200_OK
    data = join_resp.json()
    ws_path = data["ws_url"].replace("ws://localhost", "")

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
    await integration_redis.set(
        "plane:abcd", plane.model_dump_json()
    )

    async with aconnect_ws(
        ws_path,
        client=integration_client,
        keepalive_ping_interval_seconds=None,
    ) as ws:
        msg = WSMessage(**await ws.receive_json())
        assert msg.type == WSMessageType.STATE_SYNC

        await ws.send_json(
            WSMessage(type="selectPlane", payload={"hex": "abcd"}).model_dump()
        )
        confirm = WSMessage(**await ws.receive_json())
        assert confirm.type == WSMessageType.PLANE_SELECTED_CONFIRM

        await ws.send_json(
            WSMessage(type="guess", payload={"airport_code": "KJFK"}).model_dump()
        )
        result = WSMessage(**await ws.receive_json())
        assert result.type == WSMessageType.ROUND_RESULT

        await ws.send_json(WSMessage(type="leave", payload={}).model_dump())

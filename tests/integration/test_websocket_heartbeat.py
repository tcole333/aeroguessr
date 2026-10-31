import time

import pytest
from httpx import AsyncClient
from httpx_ws import aconnect_ws

from backend.schemas.room import RoomCreateRequest
from backend.schemas.ws import PingPongPayload, WSMessage, WSMessageType

from .ws_helpers import wait_for_message

pytestmark = pytest.mark.integration


async def _create_room_as_host(client: AsyncClient, nickname: str) -> str:
    """Create a room hosted by ``nickname`` and return the host's WS URL."""
    create_data = RoomCreateRequest(
        host_nickname=nickname, mode="Distance", round_timeout_seconds=30
    )
    response = await client.post("/api/v0/rooms", json=create_data.model_dump())
    response.raise_for_status()
    create_resp_data = response.json()
    ws_url = create_resp_data["ws_url"]
    assert nickname in ws_url
    assert create_resp_data["room_code"] in ws_url
    return ws_url


@pytest.mark.asyncio
async def test_server_responds_to_ping_with_pong(integration_client: AsyncClient) -> None:
    """Verify server sends PONG back when client sends PING."""
    nickname = f"pingtester_{int(time.time())}"
    ws_url = await _create_room_as_host(integration_client, nickname)

    async with aconnect_ws(ws_url, client=integration_client) as ws:
        await wait_for_message(ws, WSMessageType.STATE_SYNC.value)

        ping_seq = 123
        ping_msg = WSMessage(type=WSMessageType.PING, payload=PingPongPayload(seq=ping_seq))
        await ws.send_json(ping_msg.model_dump())

        pong = await wait_for_message(ws, WSMessageType.PONG.value, timeout=2.0, seq=ping_seq)

    assert PingPongPayload.model_validate(pong["payload"]).seq == ping_seq

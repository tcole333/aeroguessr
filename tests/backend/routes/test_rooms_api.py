import pytest
from fastapi import status
from httpx import AsyncClient

from backend.schemas.core import Player
from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio


async def test_join_solo_room(test_client: AsyncClient, redis_client: RedisClient) -> None:
    response = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["room_code"].startswith("solo:")
    assert "ws_url" in data
    # Verify Redis keys exist
    assert await redis_client.exists(f"room:{data['room_code']}:meta")
    assert (
        await redis_client.hget_model(f"room:{data['room_code']}:players", "Solo", Player)
        is not None
    )

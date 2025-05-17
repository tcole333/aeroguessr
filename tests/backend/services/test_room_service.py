import pytest

from backend.schemas.core import Player, RoomMeta
from backend.schemas.game import SoloSelectionContext
from backend.services import room_service
from backend.utils.redis_async import RedisClient


@pytest.mark.asyncio
async def test_create_solo_room_instance(redis_client: RedisClient) -> None:
    code, meta = await room_service.create_solo_room_instance("Solo", redis_client)
    assert code.startswith("solo:")
    assert meta.is_solo is True
    stored_meta = await redis_client.get_model(f"room:{code}:meta", RoomMeta)
    assert stored_meta is not None
    player = await redis_client.hget_model(f"room:{code}:players", "Solo", Player)
    assert player is not None


@pytest.mark.asyncio
async def test_solo_selection_context_helpers(redis_client: RedisClient) -> None:
    ctx = SoloSelectionContext(
        selected_plane_hex="abc",
        correct_airport_code="JFK",
        guess_direction="origin",
    )
    await room_service.set_solo_player_selection_context(redis_client, "solo:ctx", ctx)
    fetched = await room_service.get_solo_player_selection_context(redis_client, "solo:ctx")
    assert fetched == ctx
    await room_service.clear_solo_player_selection_context(redis_client, "solo:ctx")
    assert await room_service.get_solo_player_selection_context(redis_client, "solo:ctx") is None

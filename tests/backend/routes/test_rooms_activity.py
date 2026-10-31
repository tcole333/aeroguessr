"""Which player actions count as gameplay activity for the enrichment gate.

Every test runs against fakeredis, and against real Redis when integration tests
are selected (``-m integration`` with ``TEST_REDIS_URL`` pointing at a spare db).
"""

import pytest
from httpx import AsyncClient

from backend.schemas.ws import WSMessage, WSMessageType
from backend.services.presence import LAST_ACTIVITY_KEY
from backend.utils.redis_async import RedisClient
from tests.backend.routes.game_socket import game_socket
from tests.integration.planes import seed_plane

pytestmark = pytest.mark.asyncio


async def _activity_recorded(game_redis: RedisClient) -> bool:
    return await game_redis.get(LAST_ACTIVITY_KEY) is not None


async def _store_kbos_plane(game_redis: RedisClient, hex_ident: str) -> None:
    # In CI the real-Redis variants share their db with a live backend, whose broadcast
    # loop deletes stale or out-of-range planes; seed_plane keeps them fresh over Logan.
    async with await game_redis.get_connection() as conn:
        await seed_plane(conn, hex_ident, origin="KBOS", destination="KJFK")


async def test_creating_a_room_counts_as_activity(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    resp = await test_client.post("/api/v0/rooms", json={"host_nickname": "Host"})

    assert resp.status_code == 201
    assert await _activity_recorded(game_redis)


async def test_joining_a_room_counts_as_activity(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    created = await test_client.post("/api/v0/rooms", json={"host_nickname": "Host"})
    await game_redis.delete(LAST_ACTIVITY_KEY)

    resp = await test_client.post(
        f"/api/v0/rooms/{created.json()['room_code']}/join", json={"nickname": "Guest"}
    )

    assert resp.status_code == 200
    assert await _activity_recorded(game_redis)


async def test_failed_join_does_not_count_as_activity(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    resp = await test_client.post("/api/v0/rooms/ZZZZ/join", json={"nickname": "Guest"})

    assert resp.status_code == 404
    assert not await _activity_recorded(game_redis)


async def test_joining_solo_counts_as_activity(
    test_client: AsyncClient, game_redis: RedisClient
) -> None:
    resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})

    assert resp.status_code == 200
    assert await _activity_recorded(game_redis)


async def _open_game_socket(test_client: AsyncClient, game_redis: RedisClient, mode: str) -> str:
    """Create a solo or multiplayer room with a KBOS plane, then forget the join's activity."""
    if mode == "solo":
        resp = await test_client.post("/api/v0/rooms/solo/join", json={"nickname": "Solo"})
    else:
        resp = await test_client.post("/api/v0/rooms", json={"host_nickname": "Host"})
    await _store_kbos_plane(game_redis, "abc123")
    await game_redis.delete(LAST_ACTIVITY_KEY)
    return resp.json()["ws_url"].replace("ws://testserver", "")


async def _ping_and_wait_for_pong(ws) -> None:
    """Messages are handled in order, so a pong means everything before it was handled."""
    await ws.send_json(WSMessage(type="ping", payload={"seq": 1}).model_dump())
    for _ in range(20):
        if (await ws.receive_json())["type"] == WSMessageType.PONG:
            return
    raise AssertionError("no pong")


@pytest.mark.parametrize("mode", ["solo", "multiplayer"])
@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        ("ping", {"seq": 1}),
        # An idle tab answers every server heartbeat with a pong.
        ("pong", {"seq": 1}),
        ("claimHost", {}),
        ("transferHost", {"to_nickname": "Guest"}),
    ],
)
async def test_reconnects_heartbeats_and_host_management_do_not_count_as_activity(
    test_client: AsyncClient,
    game_redis: RedisClient,
    mode: str,
    message_type: str,
    payload: dict,
) -> None:
    ws_path = await _open_game_socket(test_client, game_redis, mode)

    async with game_socket(ws_path) as ws:
        assert (await ws.receive_json())["type"] == WSMessageType.STATE_SYNC
        await ws.send_json(WSMessage(type=message_type, payload=payload).model_dump())
        await _ping_and_wait_for_pong(ws)

        assert not await _activity_recorded(game_redis)


@pytest.mark.parametrize("mode", ["solo", "multiplayer"])
async def test_leaving_does_not_count_as_activity(
    test_client: AsyncClient, game_redis: RedisClient, mode: str
) -> None:
    ws_path = await _open_game_socket(test_client, game_redis, mode)

    async with game_socket(ws_path) as ws:
        assert (await ws.receive_json())["type"] == WSMessageType.STATE_SYNC

    # game_socket sent the leave and waited until the server had finished with the socket.
    assert not await _activity_recorded(game_redis)


@pytest.mark.parametrize("mode", ["solo", "multiplayer"])
@pytest.mark.parametrize(
    ("message_type", "payload"),
    [
        ("selectPlane", {"hex": "abc123"}),
        ("startRound", {}),
        ("guess", {"airport_code": "KJFK"}),
        ("skipRound", {}),
    ],
)
async def test_gameplay_messages_count_as_activity(
    test_client: AsyncClient,
    game_redis: RedisClient,
    mode: str,
    message_type: str,
    payload: dict,
) -> None:
    ws_path = await _open_game_socket(test_client, game_redis, mode)

    async with game_socket(ws_path) as ws:
        assert (await ws.receive_json())["type"] == WSMessageType.STATE_SYNC
        await ws.send_json(WSMessage(type=message_type, payload=payload).model_dump())
        await _ping_and_wait_for_pong(ws)

        assert await _activity_recorded(game_redis)


@pytest.mark.parametrize("mode", ["solo", "multiplayer"])
async def test_a_rejected_guess_still_counts_as_activity(
    test_client: AsyncClient, game_redis: RedisClient, mode: str
) -> None:
    """Any guess attempt is a person at the keyboard, even one the server turns down.

    The gate only asks whether someone is playing; the daily cap and per-minute limit
    bound spend whatever the activity signal says.
    """
    ws_path = await _open_game_socket(test_client, game_redis, mode)

    async with game_socket(ws_path) as ws:
        assert (await ws.receive_json())["type"] == WSMessageType.STATE_SYNC
        await ws.send_json(WSMessage(type="guess", payload={"airport_code": "ZZZZ"}).model_dump())
        error = await ws.receive_json()
        await _ping_and_wait_for_pong(ws)

        assert error["type"] == WSMessageType.ERROR
        assert await _activity_recorded(game_redis)

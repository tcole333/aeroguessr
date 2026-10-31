"""RedisClient's socket timeouts (#210): a Redis that never answers fails the call in time.

Each test sets one timeout short and the other long, and fails at ``GUARD_SECONDS``. That is
far above the short timeout but below the long one and the 5 s default, so a pool that hangs,
ignores the setting or uses the wrong timeout fails the test.
"""

import asyncio
import socket
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
import redis.asyncio as redis
from redis.exceptions import TimeoutError as RedisTimeoutError

from backend.utils.redis_async import RedisClient

pytestmark = pytest.mark.asyncio

GUARD_SECONDS = 3


@pytest_asyncio.fixture
async def silent_server() -> AsyncIterator[str]:
    """A server that accepts connections and never answers; yields its redis:// URL."""
    accepted: list[asyncio.StreamWriter] = []

    async def accept(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        accepted.append(writer)

    server = await asyncio.start_server(accept, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield f"redis://127.0.0.1:{port}/0"
    for writer in accepted:
        writer.close()
    server.close()
    await server.wait_closed()


async def test_a_reply_that_never_comes_times_out(
    silent_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REDIS_URL", silent_server)
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_SECONDS", "0.3")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS", "30")
    client = RedisClient()

    async with asyncio.timeout(GUARD_SECONDS):
        with pytest.raises(RedisTimeoutError):
            await client.ping()


def _leave_a_stale_writer_on_the_next_free_fd() -> None:
    """Recreate the event-loop state behind #208's hang.

    There, a write on a dropped connection left the selector watching the closed socket's
    fd for writes. The next socket reuses that fd number, and its connect registers a writer
    through ``selector.modify()``. The event mask is unchanged, so kqueue/epoll are never
    told about the new socket and the connect never completes on its own.
    """
    doomed = socket.socket()
    fd = doomed.fileno()
    asyncio.get_running_loop().add_writer(fd, lambda: None)
    doomed.close()
    probe = socket.socket()
    assert probe.fileno() == fd, "the next socket must reuse the stale fd"
    probe.close()


@pytest.mark.integration
async def test_a_connect_that_never_completes_times_out_and_the_next_call_reconnects(
    real_redis: redis.Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = real_redis.connection_pool.connection_kwargs
    # An IP address, so the connect starts without a DNS lookup that could take the fd.
    host = socket.gethostbyname(server["host"])
    monkeypatch.setenv("REDIS_URL", f"redis://{host}:{server['port']}/{server['db']}")
    monkeypatch.setenv("REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS", "0.5")
    # redis-py falls back to the reply timeout for connects; make that fallback too slow.
    monkeypatch.setenv("REDIS_SOCKET_TIMEOUT_SECONDS", "30")
    client = RedisClient()
    _leave_a_stale_writer_on_the_next_free_fd()

    try:
        async with asyncio.timeout(GUARD_SECONDS):
            with pytest.raises(RedisTimeoutError):
                await client.ping()
        assert await client.ping()
    finally:
        await (await client.get_connection()).aclose(close_connection_pool=True)

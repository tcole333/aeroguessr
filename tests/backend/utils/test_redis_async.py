"""Tests for the Redis async utilities."""

import pytest
from fakeredis import aioredis
from pydantic import BaseModel
from pytest import MonkeyPatch
from redis.asyncio import ConnectionPool

from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


class MockModel(BaseModel):
    field1: str
    field2: int


@pytest.fixture
def mock_redis_pool(monkeypatch: MonkeyPatch) -> ConnectionPool:
    """Fixture to patch the Redis connection pool with fakeredis."""
    # Initialize FakeRedis with decode_responses=True to match production behavior
    fake_pool = aioredis.FakeRedis(decode_responses=True).connection_pool
    monkeypatch.setattr(RedisClient, "_pool", fake_pool)
    return fake_pool


async def test_set_json_no_expiry(mock_redis_pool: ConnectionPool) -> None:
    """Test setting a JSON value without expiry."""
    client = RedisClient()
    model = MockModel(field1="test", field2=123)
    key = "test:key:no_expiry"

    await client.set_json(key, model)

    conn = await client.get_connection()
    stored_data = await conn.get(key)
    ttl = await conn.ttl(key)

    assert stored_data == model.model_dump_json()
    assert ttl == -1  # No expiry


async def test_set_json_with_expiry(mock_redis_pool: ConnectionPool) -> None:
    """Test setting a JSON value with expiry."""
    client = RedisClient()
    model = MockModel(field1="expire_test", field2=456)
    key = "test:key:expiry"
    expire_seconds = 60

    await client.set_json(key, model, expire_seconds=expire_seconds)

    conn = await client.get_connection()
    stored_data = await conn.get(key)
    ttl = await conn.ttl(key)

    assert stored_data == model.model_dump_json()
    assert 0 < ttl <= expire_seconds


async def test_expire(mock_redis_pool: ConnectionPool) -> None:
    """Test setting expiry on an existing key."""
    client = RedisClient()
    key = "test:key:set_expire"
    initial_value = "some_value"
    expire_seconds = 120

    # Set an initial value without expiry
    conn = await client.get_connection()
    await conn.set(key, initial_value)

    # Set the expiry
    result = await client.expire(key, expire_seconds)
    ttl = await conn.ttl(key)

    assert result is True
    assert 0 < ttl <= expire_seconds


async def test_expire_nonexistent_key(mock_redis_pool: ConnectionPool) -> None:
    """Test setting expiry on a non-existent key."""
    client = RedisClient()
    key = "test:key:nonexistent"
    expire_seconds = 60

    result = await client.expire(key, expire_seconds)

    assert result is False

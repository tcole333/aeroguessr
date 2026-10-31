"""Tests for the Redis async utilities."""

import json

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


async def test_ping(mock_redis_pool: ConnectionPool) -> None:
    """Ping returns True when the Redis server is reachable."""
    client = RedisClient()
    assert await client.ping() is True


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


async def test_get_model_success(mock_redis_pool: ConnectionPool) -> None:
    """Test getting a model successfully."""
    client = RedisClient()
    model = MockModel(field1="get_test", field2=789)
    key = "test:key:get_success"

    # Store the model first
    await client.set_json(key, model)

    # Retrieve the model
    retrieved_model = await client.get_model(key, MockModel)

    assert retrieved_model is not None
    assert retrieved_model.field1 == model.field1
    assert retrieved_model.field2 == model.field2


async def test_get_model_nonexistent(mock_redis_pool: ConnectionPool) -> None:
    """Test getting a non-existent model."""
    client = RedisClient()
    key = "test:key:get_nonexistent"

    retrieved_model = await client.get_model(key, MockModel)

    assert retrieved_model is None


async def test_get_model_invalid_json(mock_redis_pool: ConnectionPool) -> None:
    """Test getting a model when stored data is invalid JSON."""
    client = RedisClient()
    key = "test:key:get_invalid_json"

    # Store invalid JSON directly
    conn = await client.get_connection()
    await conn.set(key, "{invalid json")

    retrieved_model = await client.get_model(key, MockModel)

    assert retrieved_model is None


async def test_get_model_wrong_schema(mock_redis_pool: ConnectionPool) -> None:
    """Test getting a model when stored data doesn't match Pydantic schema."""
    client = RedisClient()
    key = "test:key:get_wrong_schema"
    # Store JSON with missing/wrong fields
    invalid_data = {"field1": "only one field"}  # Missing field2

    conn = await client.get_connection()
    await conn.set(key, json.dumps(invalid_data))

    retrieved_model = await client.get_model(key, MockModel)

    assert retrieved_model is None


# --- Tests for Hash Methods --- #

HASH_KEY = "test:hash"


async def test_hset_model_new_field(mock_redis_pool: ConnectionPool) -> None:
    """Test hset_model creating a new field in the hash."""
    client = RedisClient()
    model = MockModel(field1="hash_test_1", field2=111)
    field = "field_a"

    result = await client.hset_model(HASH_KEY, field, model)
    assert result == 1  # Should return 1 for new field

    conn = await client.get_connection()
    stored_data = await conn.hget(HASH_KEY, field)
    assert stored_data == model.model_dump_json()


async def test_hset_model_update_field(mock_redis_pool: ConnectionPool) -> None:
    """Test hset_model updating an existing field in the hash."""
    client = RedisClient()
    field = "field_b"
    model1 = MockModel(field1="hash_test_2_v1", field2=222)
    model2 = MockModel(field1="hash_test_2_v2", field2=223)

    # Set initial value
    await client.hset_model(HASH_KEY, field, model1)
    # Update value
    result = await client.hset_model(HASH_KEY, field, model2)
    assert result == 0  # Should return 0 for updated field

    conn = await client.get_connection()
    stored_data = await conn.hget(HASH_KEY, field)
    assert stored_data == model2.model_dump_json()


async def test_hget_model_success(mock_redis_pool: ConnectionPool) -> None:
    """Test hget_model retrieving a model successfully."""
    client = RedisClient()
    field = "field_c"
    model = MockModel(field1="hash_get_success", field2=333)

    # Store the model first
    await client.hset_model(HASH_KEY, field, model)

    retrieved_model = await client.hget_model(HASH_KEY, field, MockModel)
    assert retrieved_model is not None
    assert retrieved_model == model


async def test_hget_model_nonexistent_field(mock_redis_pool: ConnectionPool) -> None:
    """Test hget_model retrieving a non-existent field."""
    client = RedisClient()
    retrieved_model = await client.hget_model(HASH_KEY, "nonexistent_field", MockModel)
    assert retrieved_model is None


async def test_hget_model_nonexistent_hash(mock_redis_pool: ConnectionPool) -> None:
    """Test hget_model retrieving from a non-existent hash."""
    client = RedisClient()
    retrieved_model = await client.hget_model("nonexistent_hash", "any_field", MockModel)
    assert retrieved_model is None


async def test_hget_model_invalid_json(mock_redis_pool: ConnectionPool) -> None:
    """Test hget_model when stored data is invalid JSON."""
    client = RedisClient()
    field = "field_invalid_json"

    # Store invalid JSON directly
    conn = await client.get_connection()
    await conn.hset(HASH_KEY, field, "{invalid json")

    retrieved_model = await client.hget_model(HASH_KEY, field, MockModel)
    assert retrieved_model is None


async def test_hget_model_wrong_schema(mock_redis_pool: ConnectionPool) -> None:
    """Test hget_model when stored data doesn't match Pydantic schema."""
    client = RedisClient()
    field = "field_wrong_schema"
    invalid_data = {"field1": "only one field"}  # Missing field2

    conn = await client.get_connection()
    await conn.hset(HASH_KEY, field, json.dumps(invalid_data))

    retrieved_model = await client.hget_model(HASH_KEY, field, MockModel)
    assert retrieved_model is None


async def test_hgetall_models_success(mock_redis_pool: ConnectionPool) -> None:
    """Test hgetall_models retrieving multiple models successfully."""
    client = RedisClient()
    hash_key_all = "test:hash:all"
    model1 = MockModel(field1="all_1", field2=1)
    model2 = MockModel(field1="all_2", field2=2)

    await client.hset_model(hash_key_all, "model1", model1)
    await client.hset_model(hash_key_all, "model2", model2)

    retrieved_models = await client.hgetall_models(hash_key_all, MockModel)
    assert len(retrieved_models) == 2
    assert retrieved_models["model1"] == model1
    assert retrieved_models["model2"] == model2


async def test_hgetall_models_partial_invalid(mock_redis_pool: ConnectionPool) -> None:
    """Test hgetall_models when some fields contain invalid data."""
    client = RedisClient()
    hash_key_partial = "test:hash:partial"
    model_valid = MockModel(field1="valid", field2=99)

    conn = await client.get_connection()
    await conn.hset(hash_key_partial, "valid_field", model_valid.model_dump_json())
    await conn.hset(hash_key_partial, "invalid_json_field", "{invalid")
    await conn.hset(hash_key_partial, "wrong_schema_field", '{"field1":"partial"}')

    retrieved_models = await client.hgetall_models(hash_key_partial, MockModel)
    assert len(retrieved_models) == 1  # Only the valid one should be returned
    assert "valid_field" in retrieved_models
    assert retrieved_models["valid_field"] == model_valid
    assert "invalid_json_field" not in retrieved_models
    assert "wrong_schema_field" not in retrieved_models


async def test_hgetall_models_empty(mock_redis_pool: ConnectionPool) -> None:
    """Test hgetall_models on an empty or non-existent hash."""
    client = RedisClient()
    retrieved_models_nonexistent = await client.hgetall_models(
        "nonexistent_hash_for_all", MockModel
    )
    assert retrieved_models_nonexistent == {}

    hash_key_empty = "test:hash:empty_for_all"
    await client.hset_model(hash_key_empty, "temp", MockModel(field1="t", field2=1))
    await client.hset_model(hash_key_empty, "temp", MockModel(field1="t", field2=1))  # update
    conn = await client.get_connection()
    await conn.hdel(hash_key_empty, "temp")  # make it empty
    retrieved_models_empty = await client.hgetall_models(hash_key_empty, MockModel)
    assert retrieved_models_empty == {}


# --- Test for Exists --- #


async def test_exists_true(mock_redis_pool: ConnectionPool) -> None:
    """Test exists method when key exists."""
    client = RedisClient()
    key = "test:exists:true"
    conn = await client.get_connection()
    await conn.set(key, "value")

    assert await client.exists(key) is True


async def test_exists_false(mock_redis_pool: ConnectionPool) -> None:
    """Test exists method when key does not exist."""
    client = RedisClient()
    key = "test:exists:false"

    assert await client.exists(key) is False

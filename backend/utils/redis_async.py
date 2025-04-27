"""Asynchronous Redis client utilities."""

import json
import logging
import os
from typing import Dict, Optional, Type, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel

T_BaseModel = TypeVar("T_BaseModel", bound=BaseModel)

logger = logging.getLogger(__name__)


class RedisClient:
    """A wrapper around redis.asyncio for common operations."""

    # NOTE:  We purposely keep the pool *per instance* instead of at
    #        class-level because a single `redis.ConnectionPool` is tightly
    #        coupled to the asyncio event-loop in which it was created.  In
    #        pytest we get a fresh event-loop for every test function (see
    #        `pytest-asyncio` docs).  Re-using a global pool therefore leads
    #        to *"Future attached to a different loop"* runtime errors when a
    #        connection that was spawned in Loop-A is awaited in Loop-B.  The
    #        lightweight nature of a pool (<1 kB) means instantiating it per
    #        client has negligible overhead in the context of web requests.

    _pool: Optional[redis.ConnectionPool] = None  # instance-scoped now

    def __init__(self, redis_instance: Optional[redis.Redis] | None = None) -> None:
        """Create a new Redis client wrapper.

        Args:
            redis_instance:  Inject an existing ``redis.asyncio.Redis`` (or
                *fakeredis* replacement) connection.  Passing this is handy
                in unit-tests where we don't want to talk to a real Redis
                server.  When supplied, the wrapper will *always* return this
                connection from :py:meth:`get_connection` and ignore the
                internal pool.
        """

        self._external_connection: Optional[redis.Redis] = redis_instance

        # Maintain backward-compat attribute that tests were setting directly.
        # e.g. ``client_wrapper.redis = FakeRedis()`` – if assigned we'll use
        # it as the external connection as well.
        if redis_instance is not None:
            self.redis = redis_instance  # type: ignore[attr-defined]

    # ---------------------------------------------------------------------
    # Connection helpers
    # ---------------------------------------------------------------------

    def _get_pool(self) -> redis.ConnectionPool:
        """Lazily create (or return) the connection pool for **this** instance."""
        if self._pool is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
        return self._pool

    async def get_connection(self) -> redis.Redis:  # noqa: D401 – *get* is ok
        """Return a ``redis.asyncio.Redis`` connection ready for ``await``-ing."""
        # 1.  If the consumer (e.g. a unit-test) injected a stand-in connection
        #     use that verbatim.
        external = getattr(self, "redis", None) or self._external_connection
        if external is not None:
            return external

        # 2.  Otherwise create one from (or borrow via) the per-instance pool.
        return redis.Redis(connection_pool=self._get_pool())

    async def set_json(
        self,
        key: str,
        model: BaseModel,
        expire_seconds: Optional[int] = None,
    ) -> None:
        """Serialize a Pydantic model to JSON and store it in Redis.

        Args:
            key: The Redis key.
            model: The Pydantic model instance to store.
            expire_seconds: Optional TTL in seconds.
        """
        async with await self.get_connection() as conn:
            json_data = model.model_dump_json()
            await conn.set(key, json_data, ex=expire_seconds)

    async def get_model(self, key: str, model_type: Type[T_BaseModel]) -> Optional[T_BaseModel]:
        """Retrieve a JSON string from Redis and deserialize it into a Pydantic model.

        Args:
            key: The Redis key.
            model_type: The Pydantic model class to deserialize into.

        Returns:
            An instance of the model_type if the key exists and deserialization succeeds,
            otherwise None.
        """
        async with await self.get_connection() as conn:
            json_data = await conn.get(key)
            if json_data:
                try:
                    # Use model_validate_json for Pydantic v2
                    return model_type.model_validate_json(json_data)
                except (json.JSONDecodeError, ValueError) as e:
                    # Log the error appropriately in a real app
                    logger.error(f"Error deserializing key {key}: {e}")
                    return None
            return None

    async def expire(self, key: str, seconds: int) -> bool:
        """Set an expiration time on a key.

        Args:
            key: The Redis key.
            seconds: The TTL in seconds.

        Returns:
            True if the timeout was set, False otherwise.
        """
        async with await self.get_connection() as conn:
            return await conn.expire(key, seconds)  # type: ignore

    # Add methods for Hashes
    async def hset_model(self, hash_key: str, field: str, model: BaseModel) -> int:
        """Serialize a Pydantic model to JSON and store it in a Redis Hash field.

        Args:
            hash_key: The key of the Redis Hash.
            field: The field within the Hash to set.
            model: The Pydantic model instance to store.

        Returns:
            1 if field is a new field in the hash and value was set.
            0 if field already exists in the hash and the value was updated.
        """
        async with await self.get_connection() as conn:
            json_data = model.model_dump_json()
            return await conn.hset(hash_key, field, json_data)  # type: ignore

    async def hget_model(
        self, hash_key: str, field: str, model_type: Type[T_BaseModel]
    ) -> Optional[T_BaseModel]:
        """Retrieve a JSON string from a Redis Hash field and deserialize it.

        Args:
            hash_key: The key of the Redis Hash.
            field: The field within the Hash to retrieve.
            model_type: The Pydantic model class to deserialize into.

        Returns:
            An instance of the model_type if the field exists and deserialization succeeds,
            otherwise None.
        """
        async with await self.get_connection() as conn:
            # `fakeredis` may have stored the *field* as bytes – ensure we query with the right
            # representation first, then normalise the result key for downstream callers.
            query_field: str | bytes = field
            if isinstance(field, str):
                # try bytes first since underlying data might be bytes
                alt = field.encode()
                if await conn.hexists(hash_key, alt):
                    query_field = alt

            json_data = await conn.hget(hash_key, query_field)
            if json_data:
                try:
                    return model_type.model_validate_json(json_data)
                except (json.JSONDecodeError, ValueError, TypeError) as e:  # Added TypeError
                    logger.error(f"Error deserializing hash key {hash_key}, field {field}: {e}")
                    return None
            return None

    async def hgetall_models(
        self, hash_key: str, model_type: Type[T_BaseModel]
    ) -> Dict[str, T_BaseModel]:  # Used Dict
        """Retrieve all fields from a Redis Hash and deserialize them into models.

        Args:
            hash_key: The key of the Redis Hash.
            model_type: The Pydantic model class to deserialize values into.

        Returns:
            A dictionary mapping fields to deserialized model instances.
            Fields that fail deserialization are omitted.
        """
        models: Dict[str, T_BaseModel] = {}
        async with await self.get_connection() as conn:
            hash_data = await conn.hgetall(hash_key)
            for field_raw, json_data in hash_data.items():
                # Normalise field name to *str* – fakeredis returns ``bytes``
                field: str = (
                    field_raw.decode()
                    if isinstance(field_raw, (bytes, bytearray))
                    else str(field_raw)
                )
                try:
                    model = model_type.model_validate_json(json_data)
                    models[field] = model
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    logger.error(
                        "Error deserializing hash key %s, field %s: %s", hash_key, field, e
                    )
                    # Skip this field
        return models

    async def exists(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        async with await self.get_connection() as conn:
            # exists returns the number of keys that exist from the list provided
            return await conn.exists(key) > 0  # type: ignore


# Example usage (optional, for demonstration)
async def main() -> None:
    client = RedisClient()
    conn = await client.get_connection()
    await conn.ping()
    # print("Redis connection successful!") # Removed example print


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())  # type: ignore

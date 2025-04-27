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

    _pool: Optional[redis.ConnectionPool] = None

    @classmethod
    def _get_pool(cls) -> redis.ConnectionPool:
        """Get the Redis connection pool, creating it if necessary."""
        if cls._pool is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            cls._pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
        return cls._pool

    @classmethod
    async def get_connection(cls) -> redis.Redis:
        """Get a Redis connection from the pool."""
        return redis.Redis(connection_pool=cls._get_pool())

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
            json_data = await conn.hget(hash_key, field)
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
            for field, json_data in hash_data.items():
                try:
                    model = model_type.model_validate_json(json_data)
                    models[field] = model
                except (json.JSONDecodeError, ValueError, TypeError) as e:  # Added TypeError
                    logger.error(f"Error deserializing hash key {hash_key}, field {field}: {e}")
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

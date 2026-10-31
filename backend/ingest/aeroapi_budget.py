"""Redis-backed spend limits for FlightAware AeroAPI.

Every request reserves its worst-case result sets *before* it is sent:

- a counter per UTC day (``aeroapi:result_sets:YYYY-MM-DD``) is capped at the
  configured daily cap;
- a per-minute limiter counts the current and the previous calendar minute
  together, so any rolling 60 seconds stays within the per-minute cap.

If either limit would be exceeded the reservation is rolled back and the
request is denied. Any Redis error also denies the request (fail closed).
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

DAY_KEY_PREFIX = "aeroapi:result_sets:"
MINUTE_KEY_PREFIX = "aeroapi:result_sets_minute:"
USAGE_KEY_PREFIX = "aeroapi:usage:"
DAY_KEY_TTL_SECONDS = 3 * 86400
MINUTE_KEY_TTL_SECONDS = 180
USAGE_KEY_TTL_SECONDS = 7 * 86400


class BudgetDenial(StrEnum):
    """Why a reservation was refused."""

    DAILY_CAP = "daily_cap"
    RATE_LIMIT = "rate_limit"
    REDIS_ERROR = "redis_error"


@dataclass(frozen=True)
class BudgetGrant:
    """A successful reservation, with today's total including it."""

    day_total: int
    daily_cap: int


def utc_day(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, tz=timezone.utc).strftime("%Y-%m-%d")


def day_key(day: str) -> str:
    return f"{DAY_KEY_PREFIX}{day}"


def usage_key(day: str) -> str:
    return f"{USAGE_KEY_PREFIX}{day}"


class AeroApiBudget:
    """Reserves AeroAPI result sets against the daily and per-minute caps."""

    def __init__(
        self,
        redis_client: RedisClient,
        daily_cap: int,
        per_minute_cap: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis_client
        self._daily_cap = daily_cap
        self._per_minute_cap = per_minute_cap
        self._clock = clock
        # Floor for the day counter in case Redis loses the key mid-run, e.g. a
        # Redis restart before its next snapshot: spend this process already
        # made today is never forgotten.
        self._local_day = ""
        self._local_day_total = 0

    async def reserve(self, endpoint: str, result_sets: int) -> BudgetGrant | BudgetDenial:
        """Reserve ``result_sets`` for one request to ``endpoint``."""
        now = self._clock()
        day = utc_day(now)
        minute = int(now // 60)
        keys = (
            day_key(day),
            f"{MINUTE_KEY_PREFIX}{minute}",
            f"{MINUTE_KEY_PREFIX}{minute - 1}",
            usage_key(day),
        )
        try:
            day_total, minute_total, previous_minute_total = await self._reserve_in_redis(
                keys, endpoint, result_sets
            )
        except Exception as e:
            logger.warning("AeroAPI budget unavailable (Redis error), denying request: %s", e)
            return BudgetDenial.REDIS_ERROR

        if day != self._local_day:
            self._local_day, self._local_day_total = day, 0
        day_total = max(day_total, self._local_day_total + result_sets)

        denial = None
        if day_total > self._daily_cap:
            denial = BudgetDenial.DAILY_CAP
        elif minute_total + previous_minute_total > self._per_minute_cap:
            denial = BudgetDenial.RATE_LIMIT
        if denial is not None:
            await self._roll_back(keys, endpoint, result_sets)
            return denial

        self._local_day_total = day_total
        return BudgetGrant(day_total=day_total, daily_cap=self._daily_cap)

    async def _reserve_in_redis(
        self, keys: tuple[str, str, str, str], endpoint: str, result_sets: int
    ) -> tuple[int, int, int]:
        day, minute, previous_minute, usage = keys
        async with await self._redis.get_connection() as conn:
            async with conn.pipeline(transaction=True) as pipe:
                pipe.incrby(day, result_sets)
                pipe.expire(day, DAY_KEY_TTL_SECONDS)
                pipe.incrby(minute, result_sets)
                pipe.expire(minute, MINUTE_KEY_TTL_SECONDS)
                pipe.get(previous_minute)
                pipe.hincrby(usage, f"{endpoint}:requests", 1)
                pipe.hincrby(usage, f"{endpoint}:result_sets", result_sets)
                pipe.expire(usage, USAGE_KEY_TTL_SECONDS)
                results = await pipe.execute()
        return int(results[0]), int(results[2]), int(results[4] or 0)

    async def _roll_back(
        self, keys: tuple[str, str, str, str], endpoint: str, result_sets: int
    ) -> None:
        day, minute, _, usage = keys
        try:
            async with await self._redis.get_connection() as conn:
                async with conn.pipeline(transaction=True) as pipe:
                    pipe.decrby(day, result_sets)
                    pipe.decrby(minute, result_sets)
                    pipe.hincrby(usage, f"{endpoint}:requests", -1)
                    pipe.hincrby(usage, f"{endpoint}:result_sets", -result_sets)
                    await pipe.execute()
        except Exception as e:
            # Leaving the counters high only makes the limits stricter.
            logger.warning("Failed to roll back denied AeroAPI reservation: %s", e)

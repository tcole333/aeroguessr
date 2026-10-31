"""AeroAPI spend limits against a real Redis (TEST_REDIS_URL)."""

import pytest

from backend.ingest.aeroapi_budget import (
    DAY_KEY_TTL_SECONDS,
    AeroApiBudget,
    BudgetDenial,
    BudgetGrant,
    day_key,
    usage_key,
)
from backend.utils.redis_async import RedisClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TODAY = "2026-10-16"


async def _day_counter(redis: RedisClient, day: str = TODAY) -> int:
    return int(await redis.get(day_key(day)) or 0)


def _budget(redis: RedisClient, clock, daily_cap: int = 25, per_minute: int = 8) -> AeroApiBudget:
    return AeroApiBudget(redis, daily_cap=daily_cap, per_minute_cap=per_minute, clock=clock)


async def test_grants_until_the_daily_cap_then_denies(
    real_redis_client: RedisClient, clock
) -> None:
    budget = _budget(real_redis_client, clock, daily_cap=5)
    outcomes = []
    for _ in range(4):
        outcomes.append(await budget.reserve("scheduled_arrivals", 2))
        clock.advance(120)

    assert [isinstance(o, BudgetGrant) for o in outcomes] == [True, True, False, False]
    assert outcomes[2] == BudgetDenial.DAILY_CAP
    assert await _day_counter(real_redis_client) == 4


async def test_denied_reservation_is_rolled_back(real_redis_client: RedisClient, clock) -> None:
    budget = _budget(real_redis_client, clock, daily_cap=3)
    await budget.reserve("scheduled_arrivals", 2)
    clock.advance(120)

    assert await budget.reserve("scheduled_arrivals", 2) == BudgetDenial.DAILY_CAP
    assert await _day_counter(real_redis_client) == 2
    assert isinstance(await budget.reserve("departures", 1), BudgetGrant)
    assert await _day_counter(real_redis_client) == 3


async def test_day_counter_expires_after_a_few_days(real_redis_client: RedisClient, clock) -> None:
    await _budget(real_redis_client, clock).reserve("departures", 1)

    conn = await real_redis_client.get_connection()
    assert 0 < await conn.ttl(day_key(TODAY)) <= DAY_KEY_TTL_SECONDS


async def test_new_utc_day_starts_a_fresh_budget(real_redis_client: RedisClient, clock) -> None:
    budget = _budget(real_redis_client, clock, daily_cap=2)
    await budget.reserve("scheduled_arrivals", 2)
    clock.advance(12 * 3600)

    assert isinstance(await budget.reserve("scheduled_arrivals", 2), BudgetGrant)
    assert await _day_counter(real_redis_client, "2026-10-17") == 2


async def test_per_minute_limit_denies_and_rolls_back(
    real_redis_client: RedisClient, clock
) -> None:
    budget = _budget(real_redis_client, clock, per_minute=8)
    for _ in range(4):
        assert isinstance(await budget.reserve("scheduled_arrivals", 2), BudgetGrant)

    assert await budget.reserve("departures", 1) == BudgetDenial.RATE_LIMIT
    assert await _day_counter(real_redis_client) == 8


async def test_per_minute_limit_holds_across_a_minute_boundary(
    real_redis_client: RedisClient, clock
) -> None:
    """Any rolling 60 s stays under the cap, not just each calendar minute."""
    budget = _budget(real_redis_client, clock, per_minute=8)
    clock.advance(29)  # 12:00:59
    for _ in range(4):
        await budget.reserve("scheduled_arrivals", 2)

    clock.advance(2)  # 12:01:01, two seconds later
    assert await budget.reserve("scheduled_arrivals", 2) == BudgetDenial.RATE_LIMIT

    clock.advance(60)  # 12:02:01, the 12:00 burst is over a minute old
    assert isinstance(await budget.reserve("scheduled_arrivals", 2), BudgetGrant)


async def test_counts_usage_per_endpoint(real_redis_client: RedisClient, clock) -> None:
    budget = _budget(real_redis_client, clock)
    await budget.reserve("scheduled_arrivals", 2)
    await budget.reserve("departures", 1)
    await budget.reserve("departures", 1)

    conn = await real_redis_client.get_connection()
    assert await conn.hgetall(usage_key(TODAY)) == {
        "scheduled_arrivals:requests": "1",
        "scheduled_arrivals:result_sets": "2",
        "departures:requests": "2",
        "departures:result_sets": "2",
    }


async def test_spend_survives_the_counter_being_evicted(
    real_redis_client: RedisClient, clock
) -> None:
    """Redis losing the key mid-run (e.g. a restart) must not reopen the budget."""
    budget = _budget(real_redis_client, clock, daily_cap=4)
    await budget.reserve("scheduled_arrivals", 2)
    await budget.reserve("scheduled_arrivals", 2)
    await real_redis_client.delete(day_key(TODAY))
    clock.advance(120)

    assert await budget.reserve("departures", 1) == BudgetDenial.DAILY_CAP

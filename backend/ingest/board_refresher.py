"""Background refresher that keeps the local airport board current while people play.

Spend scales with time spent playing, not with the number of planes:

- arrivals come from ``scheduled_arrivals`` (which includes en-route flights),
  fetched forward so the board always covers the next 20+ minutes of landings;
- departures come from ``scheduled_departures`` before they leave, so a plane
  is already on the board when it takes off; ``departures`` is asked once
  after a gap, for planes that left while the board was cold.

Each feed only asks for the stretch of time it has not covered yet, in one or
two pages. Nothing is requested while the enrichment gate is closed.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from backend.ingest.aeroapi_budget import AeroApiBudget, BudgetDenial, utc_day
from backend.ingest.aeroapi_client import AeroApiClient, BoardEndpoint, BoardPage, FetchFailure
from backend.ingest.airport_board import (
    AirportBoard,
    BoardDirection,
    FakeAirportBoard,
    RouteLookup,
    estimated_landing_times,
    parse_board_rows,
)
from backend.ingest.enrichment_config import (
    ARRIVALS_COLD_PAGES,
    DEPARTURES_COLD_PAGES,
    RECENT_DEPARTURES_PAGES,
    WARM_PAGES,
    EnrichmentConfig,
)
from backend.ingest.enrichment_gate import EnrichmentGate, GateReason, static_gate_reason
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)

MINUTE = 60.0
TICK_SECONDS = 15.0

ARRIVALS_LOOKBACK = 15 * MINUTE
ARRIVALS_HORIZON = 90 * MINUTE
ARRIVALS_REFRESH_LEAD = 20 * MINUTE
ARRIVALS_OVERLAP = 5 * MINUTE

DEPARTURES_LOOKBACK = 60 * MINUTE  # delayed flights stay "scheduled" until they leave
DEPARTURES_STEP = 20 * MINUTE
DEPARTURES_REFRESH_LEAD = 10 * MINUTE
RECENT_DEPARTURES_LOOKBACK = 45 * MINUTE

# After a cold fetch the board counts as covered at least this far ahead, so
# a busy, truncated first page is followed by a warm step rather than a refetch.
COLD_MIN_COVERAGE = 5 * MINUTE
# Every successful fetch moves coverage at least this far, so a truncated page
# whose rows do not reach past the old coverage cannot trigger a request every
# tick; at worst a feed is fetched once per step.
MIN_COVERAGE_STEP = 10 * MINUTE
FAILURE_BACKOFF_BASE = 60.0
FAILURE_BACKOFF_MAX = 15 * MINUTE
BUDGET_RETRY_SECONDS = 60.0


def failure_backoff(consecutive_failures: int) -> float:
    """Seconds to wait after this many failures in a row: 60 s doubling to 15 min."""
    return min(FAILURE_BACKOFF_BASE * 2 ** (consecutive_failures - 1), FAILURE_BACKOFF_MAX)


class Feed(StrEnum):
    ARRIVALS = "arrivals"
    DEPARTURES = "departures"
    RECENT_DEPARTURES = "recent_departures"


@dataclass
class FeedState:
    """How far ahead a feed is covered, and when it may next be fetched."""

    covered_until: float | None = None
    next_attempt_at: float = 0.0


@dataclass(frozen=True)
class BoardRequest:
    feed: Feed
    endpoint: BoardEndpoint
    direction: BoardDirection
    start: float
    end: float
    max_pages: int
    cold: bool


def plan_requests(now: float, arrivals: FeedState, departures: FeedState) -> list[BoardRequest]:
    """The board requests needed right now (usually none)."""
    requests = []
    if now >= arrivals.next_attempt_at:
        covered = arrivals.covered_until
        if covered is None or covered <= now:
            requests.append(
                BoardRequest(
                    Feed.ARRIVALS,
                    BoardEndpoint.SCHEDULED_ARRIVALS,
                    BoardDirection.ARRIVAL,
                    start=now - ARRIVALS_LOOKBACK,
                    end=now + ARRIVALS_HORIZON,
                    max_pages=ARRIVALS_COLD_PAGES,
                    cold=True,
                )
            )
        elif covered < now + ARRIVALS_REFRESH_LEAD:
            requests.append(
                BoardRequest(
                    Feed.ARRIVALS,
                    BoardEndpoint.SCHEDULED_ARRIVALS,
                    BoardDirection.ARRIVAL,
                    start=covered - ARRIVALS_OVERLAP,
                    end=now + ARRIVALS_HORIZON,
                    max_pages=WARM_PAGES,
                    cold=False,
                )
            )
    if now >= departures.next_attempt_at:
        covered = departures.covered_until
        if covered is None or covered <= now:
            requests.append(
                BoardRequest(
                    Feed.DEPARTURES,
                    BoardEndpoint.SCHEDULED_DEPARTURES,
                    BoardDirection.DEPARTURE,
                    start=now - DEPARTURES_LOOKBACK,
                    end=now + DEPARTURES_STEP,
                    max_pages=DEPARTURES_COLD_PAGES,
                    cold=True,
                )
            )
            requests.append(
                BoardRequest(
                    Feed.RECENT_DEPARTURES,
                    BoardEndpoint.DEPARTURES,
                    BoardDirection.DEPARTURE,
                    start=now - RECENT_DEPARTURES_LOOKBACK,
                    end=now,
                    max_pages=RECENT_DEPARTURES_PAGES,
                    cold=True,
                )
            )
        elif covered < now + DEPARTURES_REFRESH_LEAD:
            requests.append(
                BoardRequest(
                    Feed.DEPARTURES,
                    BoardEndpoint.SCHEDULED_DEPARTURES,
                    BoardDirection.DEPARTURE,
                    start=covered,
                    end=covered + DEPARTURES_STEP,
                    max_pages=WARM_PAGES,
                    cold=False,
                )
            )
    return requests


def next_coverage(
    request: BoardRequest,
    estimated_landings: list[float],
    truncated: bool,
    previous: float | None,
    now: float,
) -> float:
    """How far a feed is covered after a successful fetch.

    A complete answer covers the whole window. A truncated arrivals answer is
    ordered by estimated landing time, so it covers up to its last estimated
    landing, never past the requested window; a truncated answer with no
    estimates, or a truncated departures answer, is credited with half its window.
    """
    if not truncated:
        covered = request.end
    elif request.feed is Feed.ARRIVALS and estimated_landings:
        covered = min(max(estimated_landings), request.end)
    else:
        covered = request.start + (request.end - request.start) / 2
    floor = (
        previous if previous is not None and previous > now else request.start
    ) + MIN_COVERAGE_STEP
    if request.cold:
        floor = max(floor, now + COLD_MIN_COVERAGE)
    return max(covered, floor)


class BoardRefresher:
    """Fetches board pages on a timer, only while the enrichment gate is open."""

    def __init__(
        self,
        board: AirportBoard,
        client: AeroApiClient,
        gate: EnrichmentGate,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._board = board
        self._client = client
        self._gate = gate
        self._clock = clock
        self._feeds = {Feed.ARRIVALS: FeedState(), Feed.DEPARTURES: FeedState()}
        self._last_reason: GateReason | None = None
        self._cap_warned_day = ""
        self._rate_limited = False
        self._failures = 0

    async def tick(self) -> None:
        """Evaluate the gate and send whatever board requests are due."""
        now = self._clock()
        reason = await self._gate.evaluate()
        if reason is not self._last_reason:
            logger.info("AeroAPI enrichment gate: %s", reason.value)
            self._last_reason = reason
        if reason is not GateReason.OPEN:
            return

        arrivals, departures = self._feeds[Feed.ARRIVALS], self._feeds[Feed.DEPARTURES]
        for request in plan_requests(now, arrivals, departures):
            outcome = await self._client.fetch_board(
                request.endpoint, request.start, request.end, request.max_pages
            )
            if not self._record_outcome(request, outcome, now):
                break
        self._board.purge(now)

    async def run_forever(
        self,
        interval: float = TICK_SECONDS,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        """Tick forever; an unexpected error backs off like a failed fetch."""
        crashes = 0
        while True:
            try:
                await self.tick()
                crashes = 0
            except Exception:
                crashes += 1
                logger.exception("AeroAPI board refresh failed")
            await sleep(max(interval, failure_backoff(crashes)) if crashes else interval)

    def _record_outcome(
        self, request: BoardRequest, outcome: BoardPage | BudgetDenial | FetchFailure, now: float
    ) -> bool:
        """Apply one fetch outcome; False means stop sending requests this tick."""
        rate_limited = outcome is BudgetDenial.RATE_LIMIT
        if rate_limited and not self._rate_limited:
            logger.info("AeroAPI per-minute limit reached; board requests wait for it")
        self._rate_limited = rate_limited

        if isinstance(outcome, BoardPage):
            flights = parse_board_rows(outcome.rows, request.direction, self._board.airport_icao)
            self._board.merge(flights)
            if request.feed is not Feed.RECENT_DEPARTURES:
                state = self._feeds[
                    Feed.ARRIVALS if request.feed is Feed.ARRIVALS else Feed.DEPARTURES
                ]
                state.covered_until = next_coverage(
                    request,
                    estimated_landing_times(outcome.rows),
                    outcome.truncated,
                    state.covered_until,
                    now,
                )
            self._failures = 0
            logger.debug("Board %s: %d usable rows", request.feed.value, len(flights))
            return True
        if rate_limited or outcome is FetchFailure.PAUSED:
            return False
        if isinstance(outcome, BudgetDenial):
            if outcome is BudgetDenial.DAILY_CAP and self._cap_warned_day != utc_day(now):
                self._cap_warned_day = utc_day(now)
                logger.warning("AeroAPI daily result-set cap reached; no requests until 00:00 UTC")
            self._hold_all_feeds(now + BUDGET_RETRY_SECONDS)
            return False
        # Failures are usually not specific to one board (outage, key, request
        # shape), so every feed waits rather than each spending its own retries.
        self._failures += 1
        backoff = failure_backoff(self._failures)
        self._hold_all_feeds(now + backoff)
        logger.warning(
            "AeroAPI %s fetch failed (%s); no board requests for %.0fs",
            request.endpoint.value,
            outcome.value,
            backoff,
        )
        return False

    def _hold_all_feeds(self, until: float) -> None:
        for feed_state in self._feeds.values():
            feed_state.next_attempt_at = max(feed_state.next_attempt_at, until)


def build_route_source(
    config: EnrichmentConfig, redis_client: RedisClient
) -> tuple[RouteLookup, BoardRefresher | None]:
    """The route lookup ``handle_message`` uses, plus the refresher that feeds it (if any)."""
    if config.fake_adsb:
        logger.info("FAKE_ADSB: routes come from the local fake board; AeroAPI is never called")
        return FakeAirportBoard(config.airport_icao), None
    board = AirportBoard(config.airport_icao)
    reason = static_gate_reason(config)
    if reason is not None:
        logger.info("AeroAPI board refresh is off (%s); planes will have no routes", reason.value)
        return board, None
    budget = AeroApiBudget(redis_client, config.daily_result_set_cap, config.result_sets_per_minute)
    client = AeroApiClient(config.api_key, budget, config.airport_icao)
    return board, BoardRefresher(board, client, EnrichmentGate(redis_client, config))

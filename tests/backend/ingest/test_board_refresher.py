"""Board refresher + enrichment gate against a real Redis and a mock AeroAPI."""

import asyncio
import logging
from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest

from backend.ingest.aeroapi_budget import AeroApiBudget
from backend.ingest.aeroapi_client import AeroApiClient
from backend.ingest.airport_board import AirportBoard
from backend.ingest.board_refresher import ARRIVALS_REFRESH_LEAD, TICK_SECONDS, BoardRefresher
from backend.ingest.enrichment_config import EnrichmentConfig
from backend.ingest.enrichment_gate import EnrichmentGate, GateReason
from backend.services.presence import publish_active_rooms, record_gameplay_activity
from backend.utils.redis_async import RedisClient

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.integration,
    pytest.mark.usefixtures("private_presence_keys"),
]

OPEN_CONFIG = EnrichmentConfig(api_key="test-key")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeKbosBoards:
    """Mock AeroAPI: one inbound and one outbound flight around the requested window.

    ``status`` answers every request; ``failing`` lists endpoints that get a 500.
    """

    def __init__(self, clock, status: int = 200, failing: tuple[str, ...] = ()) -> None:
        self.clock = clock
        self.status = status
        self.failing = failing
        self.requests: list[httpx.Request] = []

    def endpoints(self) -> list[str]:
        return [r.url.path.rsplit("/", 1)[-1] for r in self.requests]

    def result_sets(self) -> int:
        return sum(int(r.url.params["max_pages"]) for r in self.requests)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint in self.failing:
            return httpx.Response(500, json={})
        if self.status != 200:
            return httpx.Response(self.status, json={})
        now = self.clock()
        if endpoint == "scheduled_arrivals":
            rows = [
                {
                    "fa_flight_id": "JBU123-1",
                    "ident": "JBU123",
                    "operator_icao": "JBU",
                    "origin": {"code_icao": "KMCO"},
                    "destination": {"code_icao": "KBOS"},
                    "estimated_on": _iso(now + 600),
                }
            ]
        else:
            rows = [
                {
                    "fa_flight_id": f"DAL456-{endpoint}",
                    "ident": "DAL456",
                    "operator_icao": "DAL",
                    "origin": {"code_icao": "KBOS"},
                    "destination": {"code_icao": "KATL"},
                    "estimated_off": _iso(now - 300),
                }
            ]
        return httpx.Response(200, json={endpoint: rows, "links": None, "num_pages": 1})


class BusyKbosBoards:
    """Mock AeroAPI for a busy KBOS: every answer is full and says more pages exist.

    With ``in_time_order`` the rows run forward from the window start, 40 flights
    an hour, as the design assumes. Without it every row sits at the window start,
    as if a board were not sorted by time, so a page never moves coverage forward.
    """

    ROWS_PER_PAGE = 15
    SPACING_SECONDS = 90

    def __init__(self, in_time_order: bool) -> None:
        self.in_time_order = in_time_order
        self.requests: list[httpx.Request] = []

    def result_sets(self) -> int:
        return sum(int(r.url.params["max_pages"]) for r in self.requests)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        endpoint = request.url.path.rsplit("/", 1)[-1]
        start = datetime.fromisoformat(request.url.params["start"].replace("Z", "+00:00"))
        pages = int(request.url.params["max_pages"])
        arriving = endpoint == "scheduled_arrivals"
        rows = []
        for i in range(self.ROWS_PER_PAGE * pages):
            offset = i * self.SPACING_SECONDS if self.in_time_order else 0
            when = _iso(start.timestamp() + offset)
            rows.append(
                {
                    "fa_flight_id": f"{endpoint}-{when}-{i}",
                    "ident": f"JBU{i + 100}",
                    "origin": {"code_icao": "KMCO" if arriving else "KBOS"},
                    "destination": {"code_icao": "KBOS" if arriving else "KMCO"},
                    "estimated_on" if arriving else "estimated_off": when,
                }
            )
        return httpx.Response(
            200, json={endpoint: rows, "links": {"next": "/more"}, "num_pages": pages}
        )


class TruncatedArrivalsWithOneLateRow:
    """Mock AeroAPI: a truncated arrivals page of 29 landings over the next 40 minutes,
    plus one row with no estimate whose scheduled time is four hours out.
    Departures boards are empty and complete."""

    def __init__(self, clock) -> None:
        self.clock = clock
        self.arrivals_fetched_at: list[float] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        endpoint = request.url.path.rsplit("/", 1)[-1]
        if endpoint != "scheduled_arrivals":
            return httpx.Response(200, json={endpoint: [], "links": None, "num_pages": 1})
        now = self.clock()
        self.arrivals_fetched_at.append(now)
        rows = [
            {
                "fa_flight_id": f"JBU{i}-{now:.0f}",
                "ident": f"JBU{i}",
                "origin": {"code_icao": "KMCO"},
                "destination": {"code_icao": "KBOS"},
                "estimated_on": _iso(now + i * 40 * 60 / 28),
            }
            for i in range(29)
        ]
        rows.append(
            {
                "fa_flight_id": f"DAL9-{now:.0f}",
                "ident": "DAL9",
                "origin": {"code_icao": "KATL"},
                "destination": {"code_icao": "KBOS"},
                "estimated_on": None,
                "scheduled_on": _iso(now + 4 * 3600),
            }
        )
        return httpx.Response(
            200, json={endpoint: rows, "links": {"next": "/more"}, "num_pages": 2}
        )


async def _someone_is_playing(redis: RedisClient, clock) -> None:
    await publish_active_rooms(redis, 1)
    await record_gameplay_activity(redis, now=clock())


def _refresher(
    redis: RedisClient,
    clock,
    api: FakeKbosBoards | BusyKbosBoards,
    config: EnrichmentConfig = OPEN_CONFIG,
) -> tuple[BoardRefresher, AirportBoard]:
    board = AirportBoard("KBOS")
    budget = AeroApiBudget(
        redis, config.daily_result_set_cap, config.result_sets_per_minute, clock=clock
    )
    client = AeroApiClient(
        config.api_key, budget, "KBOS", transport=httpx.MockTransport(api.handler), clock=clock
    )
    gate = EnrichmentGate(redis, config, clock=clock)
    return BoardRefresher(board, client, gate, clock=clock), board


# --- Gate ---


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (replace(OPEN_CONFIG, enabled=False), GateReason.DISABLED),
        (replace(OPEN_CONFIG, api_key=""), GateReason.NO_API_KEY),
        (replace(OPEN_CONFIG, fake_adsb=True), GateReason.FAKE_ADSB),
        (replace(OPEN_CONFIG, errors=("bad cap",)), GateReason.CONFIG_INVALID),
    ],
)
async def test_configuration_alone_can_close_the_gate(
    real_redis_client: RedisClient, clock, config: EnrichmentConfig, expected: GateReason
) -> None:
    await _someone_is_playing(real_redis_client, clock)

    assert await EnrichmentGate(real_redis_client, config, clock=clock).evaluate() == expected


async def test_gate_is_closed_without_connected_players(
    real_redis_client: RedisClient, clock
) -> None:
    await record_gameplay_activity(real_redis_client, now=clock())

    gate = EnrichmentGate(real_redis_client, OPEN_CONFIG, clock=clock)

    assert await gate.evaluate() == GateReason.NO_PLAYERS


async def test_connected_but_never_active_player_keeps_gate_closed(
    real_redis_client: RedisClient, clock
) -> None:
    """An open tab that only answers pings is not playing."""
    await publish_active_rooms(real_redis_client, 1)

    gate = EnrichmentGate(real_redis_client, OPEN_CONFIG, clock=clock)

    assert await gate.evaluate() == GateReason.IDLE


async def test_gate_closes_after_the_idle_cutoff(real_redis_client: RedisClient, clock) -> None:
    await _someone_is_playing(real_redis_client, clock)
    gate = EnrichmentGate(real_redis_client, OPEN_CONFIG, clock=clock)

    clock.advance(14 * 60)
    assert await gate.evaluate() == GateReason.OPEN
    clock.advance(2 * 60)
    assert await gate.evaluate() == GateReason.IDLE


# --- Refresher ---


@pytest.mark.parametrize(
    ("config", "playing", "active"),
    [
        (replace(OPEN_CONFIG, enabled=False), True, True),
        (replace(OPEN_CONFIG, api_key=""), True, True),
        (replace(OPEN_CONFIG, fake_adsb=True), True, True),
        (replace(OPEN_CONFIG, errors=("bad cap",)), True, True),
        (OPEN_CONFIG, False, True),  # no connected player
        (OPEN_CONFIG, True, False),  # connected, but no recent activity
    ],
    ids=["disabled", "no_api_key", "fake_adsb", "config_invalid", "no_players", "idle"],
)
async def test_refresher_makes_no_calls_while_the_gate_is_closed(
    real_redis_client: RedisClient, clock, config: EnrichmentConfig, playing: bool, active: bool
) -> None:
    if playing:
        await publish_active_rooms(real_redis_client, 1)
    if active:
        await record_gameplay_activity(real_redis_client, now=clock())
    else:
        await record_gameplay_activity(real_redis_client, now=clock() - 16 * 60)
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(real_redis_client, clock, api, config)

    for _ in range(8):
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    assert api.requests == []


async def test_first_tick_fetches_each_board_once_and_fills_the_index(
    real_redis_client: RedisClient, clock
) -> None:
    await _someone_is_playing(real_redis_client, clock)
    api = FakeKbosBoards(clock)
    refresher, board = _refresher(real_redis_client, clock, api)

    await refresher.tick()

    assert api.endpoints() == ["scheduled_arrivals", "scheduled_departures", "departures"]
    arrival = board.lookup("JBU123", clock())
    departure = board.lookup("DAL456", clock())
    assert arrival is not None and arrival.origin_icao == "KMCO"
    assert departure is not None and departure.destination_icao == "KATL"


async def test_two_minutes_of_play_cost_only_the_first_fetch(
    real_redis_client: RedisClient, clock
) -> None:
    """Calls are bounded by board coverage, not by ticks or planes."""
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(real_redis_client, clock, api)

    for _ in range(int(120 / TICK_SECONDS)):
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    assert len(api.requests) == 3
    assert await real_redis_client.get("aeroapi:result_sets:2026-10-16") == "5"


async def test_board_is_extended_before_coverage_runs_out(
    real_redis_client: RedisClient, clock
) -> None:
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(real_redis_client, clock, api)
    await _someone_is_playing(real_redis_client, clock)
    await refresher.tick()

    clock.advance(11 * 60)  # departures were covered 20 min ahead; now under 10 min remain
    await _someone_is_playing(real_redis_client, clock)
    await refresher.tick()

    assert api.endpoints()[3:] == ["scheduled_departures"]
    assert api.requests[3].url.params["max_pages"] == "1"


async def test_refresher_stops_at_the_daily_cap(real_redis_client: RedisClient, clock) -> None:
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(
        real_redis_client, clock, api, replace(OPEN_CONFIG, daily_result_set_cap=5)
    )

    for _ in range(12):  # three hours of play, a tick every 15 minutes
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(15 * 60)

    assert len(api.requests) == 3
    assert int(await real_redis_client.get("aeroapi:result_sets:2026-10-16")) <= 5


async def test_refresher_respects_the_per_minute_limit(
    real_redis_client: RedisClient, clock
) -> None:
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(
        real_redis_client, clock, api, replace(OPEN_CONFIG, result_sets_per_minute=4)
    )
    await _someone_is_playing(real_redis_client, clock)

    await refresher.tick()

    assert api.endpoints() == ["scheduled_arrivals", "scheduled_departures"]


async def test_failed_fetches_back_off(real_redis_client: RedisClient, clock) -> None:
    api = FakeKbosBoards(clock, status=500)
    refresher, _ = _refresher(real_redis_client, clock, api)

    for _ in range(int(150 / TICK_SECONDS)):
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    # t=0: one failure stops the tick; t=60: one retry; next retry not before t=180.
    assert api.endpoints() == ["scheduled_arrivals", "scheduled_arrivals"]


@pytest.mark.parametrize("status", [400, 500])
async def test_an_hour_of_persistent_errors_spends_little(
    real_redis_client: RedisClient, clock, status: int
) -> None:
    """Retries back off to every 15 minutes and send one request each."""
    api = FakeKbosBoards(clock, status=status)
    refresher, _ = _refresher(real_redis_client, clock, api)

    for _ in range(int(3600 / TICK_SECONDS)):
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    # Attempts at t = 0, 1, 3, 7, 15, 30 and 45 minutes, 2 result sets each.
    assert len(api.requests) == 7
    assert await real_redis_client.get("aeroapi:result_sets:2026-10-16") == "14"


async def test_failed_departures_fetch_is_not_followed_by_recent_departures(
    real_redis_client: RedisClient, clock
) -> None:
    api = FakeKbosBoards(clock, failing=("scheduled_departures",))
    refresher, _ = _refresher(real_redis_client, clock, api)
    await _someone_is_playing(real_redis_client, clock)

    await refresher.tick()

    assert api.endpoints() == ["scheduled_arrivals", "scheduled_departures"]


async def test_a_stuck_per_minute_limit_is_logged_once(
    real_redis_client: RedisClient, clock, caplog: pytest.LogCaptureFixture
) -> None:
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(
        real_redis_client, clock, api, replace(OPEN_CONFIG, result_sets_per_minute=1)
    )

    with caplog.at_level(logging.INFO, logger="backend.ingest.board_refresher"):
        for _ in range(8):
            await _someone_is_playing(real_redis_client, clock)
            await refresher.tick()
            clock.advance(TICK_SECONDS)

    assert api.requests == []
    assert caplog.text.count("per-minute limit reached") == 1


async def test_unexpected_errors_back_off_instead_of_retrying_every_tick(
    real_redis_client: RedisClient, clock
) -> None:
    """An exception after a reservation must not spend again 15 s later."""
    requests: list[httpx.Request] = []

    def explode(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise RuntimeError("unexpected")

    budget = AeroApiBudget(real_redis_client, 25, 8, clock=clock)
    client = AeroApiClient(
        "test-key", budget, "KBOS", transport=httpx.MockTransport(explode), clock=clock
    )
    refresher = BoardRefresher(
        AirportBoard("KBOS"),
        client,
        EnrichmentGate(real_redis_client, OPEN_CONFIG, clock=clock),
        clock,
    )
    await _someone_is_playing(real_redis_client, clock)
    stop_at = clock() + 10 * 60

    async def fake_sleep(seconds: float) -> None:
        clock.advance(seconds)
        if clock() >= stop_at:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await refresher.run_forever(sleep=fake_sleep)

    # Attempts at t = 0, 1, 3 and 7 minutes rather than every 15 s.
    assert len(requests) == 4


async def test_no_refresh_once_players_go_idle(real_redis_client: RedisClient, clock) -> None:
    api = FakeKbosBoards(clock)
    refresher, _ = _refresher(real_redis_client, clock, api)
    await _someone_is_playing(real_redis_client, clock)
    await refresher.tick()

    clock.advance(16 * 60)  # still connected, but nothing done for 16 minutes
    await publish_active_rooms(real_redis_client, 1)
    await refresher.tick()

    assert len(api.requests) == 3


@pytest.mark.parametrize(
    "in_time_order", [True, False], ids=["time_ordered_pages", "pages_that_do_not_advance"]
)
async def test_an_hour_on_a_busy_truncated_board_stays_bounded(
    real_redis_client: RedisClient, clock, in_time_order: bool
) -> None:
    """Truncated pages never make the refresher fetch on every tick.

    Each feed is fetched at most about once per coverage step (10 minutes) once
    it has caught up, so an hour costs the cold fill plus roughly a dozen pages.
    """
    api = BusyKbosBoards(in_time_order)
    uncapped = replace(OPEN_CONFIG, daily_result_set_cap=10_000)
    refresher, _ = _refresher(real_redis_client, clock, api, uncapped)

    for _ in range(int(3600 / TICK_SECONDS)):
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    assert len(api.requests) <= 20
    assert api.result_sets() <= 22


async def test_one_late_row_on_a_truncated_page_does_not_stall_arrivals(
    real_redis_client: RedisClient, clock
) -> None:
    """The page reaches 40 minutes ahead, so arrivals are refreshed once under 20 minutes
    of that remain, not hours later."""
    api = TruncatedArrivalsWithOneLateRow(clock)
    refresher, _ = _refresher(real_redis_client, clock, api)
    started = clock()

    for _ in range(int(30 * 60 / TICK_SECONDS)):
        await _someone_is_playing(real_redis_client, clock)
        await refresher.tick()
        clock.advance(TICK_SECONDS)

    assert len(api.arrivals_fetched_at) >= 2, "arrivals were not refreshed within 30 minutes"
    first_refresh = api.arrivals_fetched_at[1] - started
    assert first_refresh <= ARRIVALS_REFRESH_LEAD + 60

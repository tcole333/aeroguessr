"""Production path end to end: key set, gate open -> board refresher -> routed planes.

Runs the real ingest loop with FAKE_ADSB off and a dummy key against the test
Redis. The synthetic generator stands in for dump1090 on a free port the OS
picks, and AeroAPI is a mock whose arrivals board lists every
callsign the generator can produce.
"""

import asyncio
import contextlib
import logging
import time

import httpx
import pytest

from backend.ingest import main as ingest_main
from backend.ingest.aeroapi_budget import day_key, utc_day
from backend.schemas.plane import PlaneState
from backend.services.presence import publish_active_rooms, record_gameplay_activity
from backend.utils.redis_async import RedisClient
from sample_data import adsb_generator

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

GENERATOR_AIRLINES = ("AAL", "DAL", "UAL", "JBU", "SWA", "BAW", "AFR")
ENRICHMENT_ENV = (
    "ENRICHMENT_ENABLED",
    "ENRICHMENT_IDLE_CUTOFF_MINUTES",
    "MONITORED_AIRPORT_ICAO",
    "AEROAPI_MONTHLY_BUDGET_USD",
    "AEROAPI_BUDGET_SAFETY_MARGIN",
    "AEROAPI_DAILY_RESULT_SET_CAP",
    "AEROAPI_RESULT_SETS_PER_MINUTE",
)


def _board_response(request: httpx.Request) -> httpx.Response:
    endpoint = request.url.path.rsplit("/", 1)[-1]
    rows = []
    if endpoint == "scheduled_arrivals":
        landing = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 600))
        rows = [
            {
                "fa_flight_id": f"{airline}{number}-live",
                "ident": f"{airline}{number}",
                "origin": {"code_icao": "KMCO"},
                "destination": {"code_icao": "KBOS"},
                "estimated_on": landing,
            }
            for airline in GENERATOR_AIRLINES
            for number in range(10, 1000)
        ]
    body = {endpoint: rows, "links": None, "num_pages": 1}
    return httpx.Response(200, json=body, request=request)


async def _routed_planes(redis: RedisClient) -> list[PlaneState]:
    conn = await redis.get_connection()
    planes = [await redis.get_model(key, PlaneState) for key in await conn.keys("plane:*")]
    return [p for p in planes if p is not None and p.origin is not None]


async def _wait_for_port(port: int) -> None:
    for _ in range(50):
        with contextlib.suppress(ConnectionRefusedError):
            _, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"synthetic generator never listened on {port}")


@pytest.mark.usefixtures("private_presence_keys")
async def test_open_gate_fills_the_board_and_routes_live_planes(
    real_redis_client: RedisClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    free_tcp_port: int,
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("FAKE_ADSB", "0")
    monkeypatch.setenv("FLIGHTAWARE_API_KEY", "test-key")
    for name in ENRICHMENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ingest_main, "ADSB_HOST", "127.0.0.1")
    monkeypatch.setattr(ingest_main, "ADSB_PORT", free_tcp_port)
    sent: list[httpx.Request] = []

    async def mock_aeroapi(
        client: httpx.AsyncClient, request: httpx.Request, **kwargs: object
    ) -> httpx.Response:
        sent.append(request)
        return _board_response(request)

    monkeypatch.setattr(httpx.AsyncClient, "send", mock_aeroapi)
    await publish_active_rooms(real_redis_client, 1)
    await record_gameplay_activity(real_redis_client)

    generator = asyncio.create_task(
        adsb_generator.run_server(filepath="synthetic", host="127.0.0.1", port=free_tcp_port)
    )
    await _wait_for_port(free_tcp_port)
    ingest_task = asyncio.create_task(ingest_main.run_ingest_loop())
    try:
        routed: list[PlaneState] = []
        for _ in range(150):  # up to 15 s; callsigns are re-sent every 5 s
            routed = await _routed_planes(real_redis_client)
            if routed:
                break
            await asyncio.sleep(0.1)
    finally:
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ingest_task
        with contextlib.suppress(asyncio.CancelledError):
            await generator
        await asyncio.sleep(0.05)  # let the generator's server close its port

    assert routed, "no live plane got a route from the board"
    for plane in routed:
        assert (plane.origin, plane.destination) == ("KMCO", "KBOS")
    assert [r.url.path.rsplit("/", 1)[-1] for r in sent] == [
        "scheduled_arrivals",
        "scheduled_departures",
        "departures",
    ]
    assert all(r.headers["x-apikey"] == "test-key" for r in sent)
    assert await real_redis_client.get(day_key(utc_day(time.time()))) == "5"
    # Plane traffic must not flood the INFO log with one line per stored message.
    assert not [r for r in caplog.records if r.name == "backend.utils.redis_async"]

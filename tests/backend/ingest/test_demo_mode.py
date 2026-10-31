"""Demo mode end to end: synthetic or replayed feed -> ingest -> planes in Redis.

Runs the real ingest, in this process or as ``python -m backend.ingest.main``, with
FAKE_ADSB and no API key against the test Redis. The ingest's own generator listens
on a free port the OS picks.
"""

import asyncio
import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from geopy.distance import geodesic

from backend.ingest import main as ingest_main
from backend.ingest.airport_board import FAKE_ORIGINS
from backend.schemas.plane import PlaneState
from backend.utils.redis_async import RedisClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

REPO_ROOT = Path(__file__).resolve().parents[3]
# Bradley International (KBDL), about 146 km from Logan. Planes around it cannot be
# Logan's, yet stay inside the 250 km range of the live backend that shares the test
# database in CI, whose broadcast loop deletes planes out of its range every second.
BRADLEY = (41.9389, -72.6832)


async def _routed_planes(redis: RedisClient) -> list[PlaneState]:
    conn = await redis.get_connection()
    planes = [await redis.get_model(key, PlaneState) for key in await conn.keys("plane:*")]
    return [p for p in planes if p is not None and p.origin is not None]


def _run_in_demo_mode(monkeypatch: pytest.MonkeyPatch, adsb_port: int) -> None:
    monkeypatch.setenv("FAKE_ADSB", "true")
    monkeypatch.setenv("FAKE_ADSB_FILE", "synthetic")
    monkeypatch.delenv("FLIGHTAWARE_API_KEY", raising=False)
    monkeypatch.setattr(ingest_main, "ADSB_PORT", adsb_port)


async def _routed_planes_from_the_ingest(redis: RedisClient) -> list[PlaneState]:
    """Run the ingest loop until it stores a plane with a route, then stop it."""
    ingest_task = asyncio.create_task(ingest_main.run_ingest_loop())
    try:
        routed: list[PlaneState] = []
        for _ in range(150):  # up to 15 s; callsigns are re-sent every 5 s
            routed = await _routed_planes(redis)
            if routed:
                break
            await asyncio.sleep(0.1)
    finally:
        for task in asyncio.all_tasks() - {asyncio.current_task()}:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ingest_task
        await asyncio.sleep(0.05)  # let the generator's server close its port

    assert routed, "no synthetic plane got a route"
    return routed


async def test_synthetic_planes_get_routes_without_any_api_calls(
    real_redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, free_tcp_port: int
) -> None:
    _run_in_demo_mode(monkeypatch, free_tcp_port)
    http_requests: list[httpx.Request] = []

    async def refuse(client: httpx.AsyncClient, request: httpx.Request, **kwargs: object) -> None:
        http_requests.append(request)
        raise AssertionError("demo mode must not make HTTP requests")

    monkeypatch.setattr(httpx.AsyncClient, "send", refuse)

    routed = await _routed_planes_from_the_ingest(real_redis_client)

    for plane in routed:
        assert plane.callsign
        assert plane.origin in FAKE_ORIGINS
        assert plane.destination == "KBOS"
    assert http_requests == []


async def test_demo_planes_fly_in_to_the_configured_airport_and_centre(
    real_redis_client: RedisClient, monkeypatch: pytest.MonkeyPatch, free_tcp_port: int
) -> None:
    """With Bradley's settings, demo traffic flies around Bradley and is routed to KBDL."""
    _run_in_demo_mode(monkeypatch, free_tcp_port)
    monkeypatch.setenv("MONITORED_AIRPORT_ICAO", "KBDL")
    monkeypatch.setattr(ingest_main, "CENTER_LAT", BRADLEY[0])
    monkeypatch.setattr(ingest_main, "CENTER_LON", BRADLEY[1])

    routed = await _routed_planes_from_the_ingest(real_redis_client)

    assert all(
        plane.destination == "KBDL" and geodesic(BRADLEY, (plane.lat, plane.lon)).km <= 45
        for plane in routed
    )


# --- The ingest as its own process, configured only through its environment ---


def _start_demo_ingest(adsb_port: int, **settings: str) -> subprocess.Popen:
    """``python -m backend.ingest.main`` with FAKE_ADSB=1, no key and only ``settings`` added.

    The environment is built from scratch, so nothing in the developer's shell or .env leaks in.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "AEROGUESSR_ENV_FILE": "",  # never the developer's .env
        "PYTHONPATH": str(REPO_ROOT),
        "REDIS_URL": os.environ["REDIS_URL"],  # the test database, set by real_redis_client
        "FAKE_ADSB": "1",
        "ADSB_PORT": str(adsb_port),
        "FLIGHTAWARE_API_KEY": "",
        **settings,
    }
    return subprocess.Popen(
        [sys.executable, "-m", "backend.ingest.main"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.wait()


async def _first_stored_planes(redis: RedisClient) -> list[PlaneState]:
    """Every plane in Redis as soon as there is one, waiting up to 10 s for the first.

    In CI a live backend shares the test database, and its broadcast loop deletes planes
    out of range of its own centre, so a key listed here can be gone before it is read.
    """
    conn = await redis.get_connection()
    for _ in range(100):
        planes = [await redis.get_model(key, PlaneState) for key in await conn.keys("plane:*")]
        if stored := [plane for plane in planes if plane is not None]:
            return stored
        await asyncio.sleep(0.1)
    raise AssertionError("the demo ingest never stored a plane")


async def test_fake_adsb_alone_flies_generated_planes_around_the_receiver(
    real_redis_client: RedisClient, free_tcp_port: int
) -> None:
    """A self-hoster sets FAKE_ADSB=1 and their location, but no FAKE_ADSB_FILE."""
    proc = _start_demo_ingest(free_tcp_port, CENTER_LAT=str(BRADLEY[0]), CENTER_LON=str(BRADLEY[1]))
    try:
        planes = await _first_stored_planes(real_redis_client)
    finally:
        _stop(proc)

    assert all(geodesic(BRADLEY, (plane.lat, plane.lon)).km <= 45 for plane in planes)


REPLAYED_HEX = "C0FFEE"


def _write_capture(path: Path) -> Path:
    """An SBS-1 capture of one plane near Logan, a fifth of a second between positions."""
    lines = [
        f"MSG,3,1,1,{REPLAYED_HEX},1,2026/10/31,12:00:00.{i * 200:03d},"
        f"2026/10/31,12:00:00.{i * 200:03d},,9000,,,{42.400 + i / 1000:.3f},-71.000,,,0,0,0,0"
        for i in range(5)
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


async def test_fake_adsb_file_replays_the_capture_it_names(
    real_redis_client: RedisClient, free_tcp_port: int, tmp_path: Path
) -> None:
    capture = _write_capture(tmp_path / "capture.sbs")
    proc = _start_demo_ingest(free_tcp_port, FAKE_ADSB_FILE=str(capture))
    try:
        planes = await _first_stored_planes(real_redis_client)
    finally:
        _stop(proc)

    assert {plane.hex_ident for plane in planes} == {REPLAYED_HEX}


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"])
async def test_the_demo_ingest_process_stops_on_signals(
    real_redis_client: RedisClient, free_tcp_port: int, sig: signal.Signals
) -> None:
    """``python -m backend.ingest.main`` with FAKE_ADSB, stopped the way supervisord and ^C do."""
    proc = _start_demo_ingest(free_tcp_port)
    try:
        await _first_stored_planes(real_redis_client)

        proc.send_signal(sig)
        try:
            exit_code = await asyncio.to_thread(proc.wait, 10)
        except subprocess.TimeoutExpired:
            exit_code = None
    finally:
        _stop(proc)

    assert exit_code is not None, f"the demo ingest ignored {sig.name}"

import asyncio
import contextlib
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List
from unittest.mock import patch

import pytest
from geopy.distance import geodesic

from backend.ingest.parser import RawMessage, parse_sbs_message
from sample_data import adsb_generator as gen

pytestmark = pytest.mark.asyncio

SEA_TAC = (47.4502, -122.3088)


class _FakeWriter:
    """Minimal drop-in replacement for ``asyncio.StreamWriter`` used in tests."""

    def __init__(self) -> None:
        self.buffer: List[bytes] = []

    def write(self, data: bytes) -> None:  # noqa: D401 (simple)
        self.buffer.append(data)

    async def drain(self) -> None:  # noqa: D401 (simple)
        # No real back-pressure in tests
        await asyncio.sleep(0)


@pytest.fixture
def local_time_in_new_york(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A local zone other than UTC, so reading a time as local time would show."""
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


async def test_parse_timestamp_reads_the_time_as_utc(local_time_in_new_york: None) -> None:
    tokens = ["MSG", "3", "1", "1", "ABCDEF", "1", "2025/05/01", "12:34:56.789"]
    ts = gen._parse_timestamp(tokens)  # type: ignore[attr-defined]
    expected = datetime(2025, 5, 1, 12, 34, 56, 789000, tzinfo=timezone.utc).timestamp()
    assert abs(ts - expected) < 0.001  # within 1 ms


async def test_parse_timestamp_invalid() -> None:
    tokens = ["MSG", "3"]  # Too short
    ts = gen._parse_timestamp(tokens)  # type: ignore[attr-defined]
    assert ts == 0.0


async def test_replay_respects_order_and_collects_lines() -> None:
    sample_lines = [
        "MSG,3,,1,ABCDEF,1,2025/05/01,12:00:00.000,2025/05/01,12:00:00.000,,,,,,",
        "MSG,3,,1,ABCDEF,1,2025/05/01,12:00:00.500,2025/05/01,12:00:00.500,,,,,,",
        "MSG,3,,1,ABCDEF,1,2025/05/01,12:00:01.000,2025/05/01,12:00:01.000,,,,,,",
    ]

    fake_writer = _FakeWriter()
    sleep_calls: List[float] = []

    async def fake_sleep(delay: float) -> None:  # noqa: D401 (simple)
        sleep_calls.append(delay)
        # Return immediately without waiting
        return

    with patch("asyncio.sleep", new=fake_sleep):
        await gen._replay(  # type: ignore[attr-defined]
            lines=sample_lines,
            writers=[fake_writer],
            speed=1.0,
            jitter=0.0,
            loop_forever=False,
        )

    # The replay should write len(lines)-1 entries (because first timestamp forms no delta)
    assert len(fake_writer.buffer) == len(sample_lines) - 1
    # Ensure order preserved
    decoded = [b.decode() for b in fake_writer.buffer]
    assert decoded == [ln + "\n" for ln in sample_lines[1:]]

    # Verify timing behavior
    # We expect alternating pattern of 0.5s delays and 0s drain() calls
    assert len(sleep_calls) == 4, "Expected 4 sleep calls (2 delays, 2 drains)"
    # Check the message delays (every other call)
    message_delays = [d for i, d in enumerate(sleep_calls) if i % 2 == 0]
    assert len(message_delays) == 2, "Expected 2 message delays"
    for delay in message_delays:
        assert pytest.approx(delay, rel=0.2) == 0.5, (
            f"Sleep delay {delay} too far from expected 0.5s"
        )


# --- Synthetic traffic carries callsigns the ingest can read ---


def _parse_tick(plane: "gen._SyntheticPlane") -> list:
    return [parse_sbs_message(line, 0.0) for line in plane.sbs_lines()]


def _km_from(center: tuple[float, float], position: RawMessage) -> float:
    return geodesic(center, (position.latitude, position.longitude)).kilometers


async def test_synthetic_plane_identifies_itself_before_its_first_position() -> None:
    plane = gen._SyntheticPlane(SEA_TAC)  # type: ignore[attr-defined]

    ident, position = _parse_tick(plane)

    assert (ident.msg_type, ident.hex_ident, ident.callsign) == (1, plane.hex_ident, plane.callsign)
    assert position.msg_type == 3
    assert position.latitude is not None and position.altitude is not None


async def test_synthetic_plane_repeats_identification_every_few_reports() -> None:
    plane = gen._SyntheticPlane(SEA_TAC)  # type: ignore[attr-defined]

    ticks = [_parse_tick(plane) for _ in range(2 * gen.SYN_IDENT_EVERY_STEPS)]

    identified = [i for i, msgs in enumerate(ticks) if msgs[0].msg_type == 1]
    assert identified == [0, gen.SYN_IDENT_EVERY_STEPS]


async def test_respawned_plane_identifies_with_its_new_callsign() -> None:
    plane = gen._SyntheticPlane(SEA_TAC)  # type: ignore[attr-defined]
    _parse_tick(plane)
    plane.alt = 0  # landed: next step respawns

    plane.step()
    ident = _parse_tick(plane)[0]

    assert (ident.msg_type, ident.callsign) == (1, plane.callsign)


# --- Synthetic traffic flies where the receiver is ---


async def test_synthetic_plane_appears_20_to_40_km_from_its_centre() -> None:
    plane = gen._SyntheticPlane(SEA_TAC)  # type: ignore[attr-defined]

    position = _parse_tick(plane)[-1]

    assert 20 <= _km_from(SEA_TAC, position) <= 40


async def test_synthetic_planes_fly_straight_in_to_their_centre() -> None:
    # Planes spawn on random bearings. Each must close on the centre by one full step per
    # tick, which only flying straight at it does; a plane aimed elsewhere falls short.
    planes = [gen._SyntheticPlane(SEA_TAC) for _ in range(12)]  # type: ignore[attr-defined]
    starts = [_km_from(SEA_TAC, _parse_tick(plane)[-1]) for plane in planes]

    for _ in range(30):
        for plane in planes:
            plane.step()

    closed = [
        start - _km_from(SEA_TAC, _parse_tick(plane)[-1])
        for plane, start in zip(planes, starts, strict=True)
    ]
    assert closed == pytest.approx([30 * gen._SYN_STEP_KM] * len(planes), abs=0.02)


async def test_synthetic_server_flies_planes_around_the_configured_centre(
    monkeypatch: pytest.MonkeyPatch, free_tcp_port: int
) -> None:
    monkeypatch.setenv("CENTER_LAT", str(SEA_TAC[0]))
    monkeypatch.setenv("CENTER_LON", str(SEA_TAC[1]))
    server_task = asyncio.create_task(
        gen.run_server(filepath="synthetic", host="127.0.0.1", port=free_tcp_port, plane_count=2)
    )
    try:
        reader, writer = await _connect_when_listening("127.0.0.1", free_tcp_port)
        positions: list[RawMessage] = []
        while len(positions) < 2:
            line = (await asyncio.wait_for(reader.readline(), timeout=10.0)).decode()
            message = parse_sbs_message(line.strip(), 0.0)
            if message is not None and message.latitude is not None:
                positions.append(message)
        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task

    assert all(_km_from(SEA_TAC, position) <= 41 for position in positions)


# --- run_server over TCP ---


async def _connect_when_listening(host: str, port: int) -> tuple:
    # A standalone generator imports the backend settings (pydantic) before it listens,
    # which takes over a second on a busy machine, and has taken over 10 s under coverage on
    # a heavily loaded one.
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            return await asyncio.open_connection(host, port)
        except ConnectionRefusedError:
            await asyncio.sleep(0.01)
    pytest.fail(f"Generator never accepted TCP connections on {host}:{port}")


async def test_run_server_streams_capture_lines_to_tcp_client(
    tmp_path: Path, free_tcp_port: int
) -> None:
    capture_lines = [
        f"MSG,3,1,1,ABC{i:03d},1,2025/05/01,12:00:00.{i * 10:03d},"
        f"2025/05/01,12:00:00.{i * 10:03d},,35000,,,42.1,-71.0,,,,"
        for i in range(4)
    ]
    capture_file = tmp_path / "capture.sbs"
    capture_file.write_text("\n".join(capture_lines) + "\n")
    host, port = "127.0.0.1", free_tcp_port

    server_task = asyncio.create_task(
        gen.run_server(
            filepath=str(capture_file), host=host, port=port, speed=1.0, loop_forever=True
        )
    )
    try:
        reader, writer = await _connect_when_listening(host, port)
        received = [
            (await asyncio.wait_for(reader.readline(), timeout=2.0)).decode().rstrip("\n")
            for _ in range(len(capture_lines))
        ]
        writer.close()
        await writer.wait_closed()
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task

    assert set(received) <= set(capture_lines)
    assert len(set(received)) >= 2


# --- Signals belong to the process that owns them ---

REPO_ROOT = Path(__file__).resolve().parents[3]

# Embeds the generator the way the FAKE_ADSB ingest does: as one task in a process whose
# main coroutine runs until the process is told to stop.
_EMBEDDING_HOST = """
import asyncio, sys
from sample_data import adsb_generator

async def main():
    port = int(sys.argv[1])
    server = adsb_generator.run_server(filepath="synthetic", host="127.0.0.1", port=port)
    asyncio.create_task(server)
    while True:
        try:
            _, writer = await asyncio.open_connection("127.0.0.1", port)
        except ConnectionRefusedError:
            await asyncio.sleep(0.05)
            continue
        writer.close()
        break
    print("ready", flush=True)
    await asyncio.Event().wait()

asyncio.run(main())
"""


def _start(args: list[str]) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, *args],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _exit_code_after(proc: subprocess.Popen, sig: signal.Signals) -> int | None:
    proc.send_signal(sig)
    try:
        return proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return None


async def _wait_until_listening(port: int) -> None:
    writer = (await _connect_when_listening("127.0.0.1", port))[1]
    writer.close()
    await writer.wait_closed()


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"])
async def test_a_process_embedding_the_generator_still_stops_on_signals(
    free_tcp_port: int, sig: signal.Signals
) -> None:
    proc = _start(["-c", _EMBEDDING_HOST, str(free_tcp_port)])
    assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"

    assert _exit_code_after(proc, sig) is not None, f"{sig.name} was swallowed"


async def test_the_standalone_generator_exits_cleanly_on_sigterm(free_tcp_port: int) -> None:
    proc = _start(["-m", "sample_data.adsb_generator", "--synthetic", "--port", str(free_tcp_port)])
    await _wait_until_listening(free_tcp_port)

    assert _exit_code_after(proc, signal.SIGTERM) == 0

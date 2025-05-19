import argparse
import asyncio
import contextlib
import gzip
import logging
import math
import os
import random
import signal
from datetime import datetime, timezone
from typing import List

from geopy.distance import geodesic

logger = logging.getLogger(__name__)

DEFAULT_HOST = os.getenv("ADSB_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("ADSB_PORT", 30003))

# --- Constants for synthetic mode --- #
# Boston Logan coordinates (approximate centre of the field)
BOS_LAT = 42.3656
BOS_LON = -71.0096
# Default synthetic traffic parameters
SYN_PLANE_COUNT = int(os.getenv("SYN_PLANE_COUNT", 3))  # 1–3 planes
SYN_STEP_SECONDS = 1.0  # Emit update every second
SYN_GROUNDSPEED_KTS = 220  # Typical mid-descent speed
SYN_DESCENT_FPM = 800  # Descent rate

# Pre-compute per-tick deltas
_SYN_STEP_KM = (SYN_GROUNDSPEED_KTS * 1.852) * (SYN_STEP_SECONDS / 3600)
_SYN_STEP_ALT = (SYN_DESCENT_FPM / 60) * SYN_STEP_SECONDS  # feet per step


class _LineWithTimestamp:
    """Internal helper holding an SBS line and its epoch timestamp."""

    __slots__ = ("line", "ts")

    def __init__(self, line: str, ts: float) -> None:
        self.line = line
        self.ts = ts


def _parse_timestamp(tokens: List[str]) -> float:
    """Parse date & time columns of an SBS/CSV line to epoch seconds.

    Args:
        tokens: Split CSV fields.

    Returns:
        Epoch seconds as ``float``. If parsing fails, returns ``0``.
    """

    try:
        # Date stored at index 6, time at 7 for MSG lines, but keep generic.
        date_idx, time_idx = 6, 7
        if len(tokens) <= max(date_idx, time_idx):
            return 0.0
        date_str, time_str = tokens[date_idx], tokens[time_idx]
        if not date_str or not time_str:
            return 0.0
        dt = datetime.strptime(f"{date_str} {time_str}", "%Y/%m/%d %H:%M:%S.%f")
        return dt.timestamp()
    except Exception:
        return 0.0


async def _replay(
    lines: List[str],
    writers: List[asyncio.StreamWriter],
    speed: float,
    jitter: float,
    loop_forever: bool,
) -> None:
    """Core coroutine that replays given **lines** to *writers* respecting timing."""

    # Pre-compute timestamps and deltas to avoid parsing during replay
    parsed: List[_LineWithTimestamp] = []
    prev_ts: float | None = None
    default_increment = 0.1  # 100ms fallback
    for ln in lines:
        tokens = ln.split(",")
        ts = _parse_timestamp(tokens)
        if ts == 0.0:
            ts = (prev_ts + default_increment) if prev_ts is not None else 0.0
        parsed.append(_LineWithTimestamp(ln, ts))
        prev_ts = ts

    while True:
        for i in range(1, len(parsed)):
            current = parsed[i]
            prev = parsed[i - 1]
            dt = max(0.0, (current.ts - prev.ts) / speed)
            if jitter:
                dt += random.uniform(-jitter, jitter) * dt
            await asyncio.sleep(dt)
            data = (current.line + "\n").encode()
            for w in writers:
                try:
                    w.write(data)
                    await w.drain()
                except Exception as e:
                    logger.warning("Writer error: %s", e)
        # Finished once – decide looping
        if not loop_forever:
            break


async def _client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """No-op handler. All sending is driven by the replay coroutine."""
    await reader.read()  # Block until client disconnects


class _SyntheticPlane:
    """Lightweight state container for a synthetic aircraft."""

    __slots__ = (
        "hex_ident",
        "callsign",
        "lat",
        "lon",
        "alt",
    )

    def __init__(self) -> None:
        self.hex_ident = "".join(random.choices("0123456789ABCDEF", k=6))
        airline = random.choice(["AAL", "DAL", "UAL", "JBU", "SWA", "BAW", "AFR"])
        self.callsign = f"{airline}{random.randint(10, 999)}"
        # Spawn 20–40 km away from BOS in a random bearing at 8–12 kft
        bearing = random.uniform(0, 360)
        start = geodesic(kilometers=random.uniform(20, 40)).destination((BOS_LAT, BOS_LON), bearing)
        self.lat, self.lon = start.latitude, start.longitude
        self.alt = random.uniform(8000, 12000)

    # Utility --------------------------------------------------------------- #
    def _initial_bearing(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the initial bearing between two points (deg)."""

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dlon = math.radians(lon2 - lon1)

        x = math.sin(dlon) * math.cos(phi2)
        y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlon)
        bearing_rad = math.atan2(x, y)
        return (math.degrees(bearing_rad) + 360) % 360

    def _distance_to_bos(self) -> float:
        return geodesic((self.lat, self.lon), (BOS_LAT, BOS_LON)).kilometers

    def step(self) -> None:
        """Advance aircraft position one tick toward BOS."""
        if self.alt <= 200 or self._distance_to_bos() < 1.0:
            # Re-spawn when "landed"
            self.__init__()
            return

        # Compute bearing to BOS
        bearing = self._initial_bearing(self.lat, self.lon, BOS_LAT, BOS_LON)
        # Move toward BOS
        dest = geodesic(kilometers=_SYN_STEP_KM).destination((self.lat, self.lon), bearing)
        self.lat, self.lon = dest.latitude, dest.longitude
        # Descend
        self.alt = max(0, self.alt - _SYN_STEP_ALT)

    # --------------------------------------------------------------------- #
    def sbs_line(self) -> str:
        """Return an SBS-1 formatted MSG (transmission type 3) line."""

        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y/%m/%d")
        time_str = now.strftime("%H:%M:%S.%f")[:-3]  # millisecond precision

        fields = [
            "MSG",  # 1 Message type
            "3",  # 2 Transmission type (3 = airborne position)
            "1",  # 3 Session ID (dummy)
            "1",  # 4 Aircraft ID (dummy)
            self.hex_ident,  # 5 Hex ident
            "0",  # 6 Flight ID (dummy)
            date_str,  # 7 Date generated
            time_str,  # 8 Time generated
            date_str,  # 9 Date logged
            time_str,  # 10 Time logged
            self.callsign,  # 11 Callsign
            f"{int(self.alt)}",  # 12 Altitude (ft)
            f"{int(SYN_GROUNDSPEED_KTS)}",  # 13 Ground speed (kt)
            "0",  # 14 Track (placeholder)
            f"{self.lat:.5f}",  # 15 Latitude
            f"{self.lon:.5f}",  # 16 Longitude
            "0",  # 17 Vertical rate
            "",  # 18 Squawk
            "0",  # 19 Alert flag
            "0",  # 20 Emergency flag
            "0",  # 21 SPI flag
            "0",  # 22 Is on ground
        ]
        return ",".join(fields)


async def _synthetic_replay(writers: List[asyncio.StreamWriter]) -> None:
    """Continuously emit synthetic SBS lines for a small fleet."""

    planes = [_SyntheticPlane() for _ in range(SYN_PLANE_COUNT)]

    while True:
        for plane in planes:
            plane.step()
            line = plane.sbs_line()
            data = (line + "\n").encode()
            for w in writers:
                try:
                    w.write(data)
                    await w.drain()
                except Exception as e:
                    logger.warning("Writer error: %s", e)
        await asyncio.sleep(SYN_STEP_SECONDS)


async def run_server(
    filepath: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    speed: float = 1.0,
    jitter: float = 0.0,
    loop_forever: bool = False,
) -> None:
    """Start TCP server in **replay** or **synthetic** mode.

    If *filepath* equals ``"synthetic"`` or the *synthetic* CLI flag is used, the
    server emits procedurally generated SBS messages for a handful of aircraft
    flying toward Boston Logan (KBOS). Otherwise, the given capture file is
    replayed verbatim.
    """

    synthetic_mode = filepath == "synthetic" or filepath is None

    # Load capture if not synthetic
    if not synthetic_mode:
        if filepath.endswith(".gz"):
            opener = gzip.open  # type: ignore[assignment]
        else:
            opener = open  # type: ignore[assignment]

        with opener(filepath, "rt", encoding="utf-8", errors="ignore") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]

        logger.info("Loaded %d lines from %s", len(lines), filepath)

    # Keep list of current writers (shared between modes)
    writers: List[asyncio.StreamWriter] = []

    async def new_conn(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writers.append(writer)
        logger.info("New client connected. Count=%d", len(writers))
        try:
            await _client_handler(reader, writer)
        finally:
            writers.remove(writer)
            writer.close()
            await writer.wait_closed()
            logger.info("Client disconnected. Count=%d", len(writers))

    server = await asyncio.start_server(new_conn, host, port)
    logger.info("ADS-B sample generator listening on %s:%s", host, port)

    # Handle graceful shutdown via signals (works only in main thread)
    stop_event = asyncio.Event()

    def _signal_handler(_: signal.Signals) -> None:  # type: ignore[type-var]
        logger.info("Received termination signal – shutting down generator.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(ValueError):
            loop.add_signal_handler(sig, _signal_handler, sig)  # type: ignore[arg-type]

    # Start appropriate coroutine
    if synthetic_mode:
        logger.info(
            "Starting **synthetic** ADS-B generator: %d planes, step %.1fs",
            SYN_PLANE_COUNT,
            SYN_STEP_SECONDS,
        )
        replay_task = asyncio.create_task(_synthetic_replay(writers))
    else:
        replay_task = asyncio.create_task(
            _replay(lines, writers, speed=speed, jitter=jitter, loop_forever=loop_forever)
        )

    # Convert stop_event.wait to a Task so asyncio.wait accepts it
    stop_wait_task = asyncio.create_task(stop_event.wait())

    # Wait until either the replay finishes (non-loop mode) or shutdown signal.
    await asyncio.wait(
        {replay_task, stop_wait_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Cancel whichever task is still running and wait for graceful exit
    replay_task.cancel()
    stop_wait_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await replay_task
        await stop_wait_task

    server.close()
    await server.wait_closed()


async def _async_cli(args: argparse.Namespace) -> None:
    filepath = "synthetic" if args.synthetic else args.file

    await run_server(
        filepath=filepath,
        host=args.host,
        port=args.port,
        speed=args.speed,
        jitter=args.jitter,
        loop_forever=args.loop,
    )


def _sync_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Replay an SBS (.sbs or .sbs.gz) capture over TCP for testing.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to .sbs[.gz] capture file to replay")
    group.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate synthetic traffic inbound to KBOS instead of replaying a file",
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default: %(default)s)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help="Bind port (default: %(default)s)"
    )
    parser.add_argument(
        "--speed", type=float, default=1.0, help="Replay speed factor (e.g. 2 = 2× faster)"
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop the capture indefinitely until terminated",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=0.0,
        help="Relative jitter fraction to apply to each inter-line delay (0-1)",
    )

    args = parser.parse_args()

    try:
        asyncio.run(_async_cli(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    _sync_main()

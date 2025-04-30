import argparse
import asyncio
import contextlib
import gzip
import logging
import os
import random
import signal
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_HOST = os.getenv("ADSB_HOST", "localhost")
DEFAULT_PORT = int(os.getenv("ADSB_PORT", 30003))


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
    prev_ts = None
    for ln in lines:
        tokens = ln.split(",")
        ts = _parse_timestamp(tokens)
        if ts == 0.0 and prev_ts is not None:
            ts = prev_ts  # fallback – keep constant dt
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


async def run_server(
    filepath: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    speed: float = 1.0,
    jitter: float = 0.0,
    loop_forever: bool = False,
) -> None:
    """Start TCP server and replay SBS file.

    This coroutine completes when the replay finishes (unless *loop_forever* is
    ``True``). It can be **awaited** in tests.
    """

    # Read lines (gzip-aware)
    if filepath.endswith(".gz"):
        opener = gzip.open  # type: ignore[assignment]
    else:
        opener = open  # type: ignore[assignment]

    with opener(filepath, "rt", encoding="utf-8", errors="ignore") as fh:
        lines = [ln.rstrip("\n") for ln in fh if ln.strip()]

    logger.info("Loaded %d lines from %s", len(lines), filepath)

    # Keep list of current writers
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

    # Start replay coroutine
    replay_task = asyncio.create_task(
        _replay(lines, writers, speed=speed, jitter=jitter, loop_forever=loop_forever)
    )

    await stop_event.wait()
    replay_task.cancel()
    await server.wait_closed()


async def _async_cli(args: argparse.Namespace) -> None:
    await run_server(
        filepath=args.file,
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
    parser.add_argument("--file", required=True, help="Path to .sbs[.gz] capture file")
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

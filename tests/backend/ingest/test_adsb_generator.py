import asyncio
from datetime import datetime
from typing import List
from unittest.mock import patch

import pytest

from sample_data import adsb_generator as gen

pytestmark = pytest.mark.asyncio


class _FakeWriter:
    """Minimal drop-in replacement for ``asyncio.StreamWriter`` used in tests."""

    def __init__(self) -> None:
        self.buffer: List[bytes] = []

    def write(self, data: bytes) -> None:  # noqa: D401 (simple)
        self.buffer.append(data)

    async def drain(self) -> None:  # noqa: D401 (simple)
        # No real back-pressure in tests
        await asyncio.sleep(0)


async def test_parse_timestamp_valid() -> None:
    tokens = ["MSG", "3", "1", "1", "ABCDEF", "1", "2025/05/01", "12:34:56.789"]
    ts = gen._parse_timestamp(tokens)  # type: ignore[attr-defined]
    expected = datetime.strptime("2025/05/01 12:34:56.789", "%Y/%m/%d %H:%M:%S.%f").timestamp()
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
        assert (
            pytest.approx(delay, rel=0.2) == 0.5
        ), f"Sleep delay {delay} too far from expected 0.5s"

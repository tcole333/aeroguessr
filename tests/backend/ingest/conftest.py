"""Fixtures for the ingest tests.

Real Redis comes from the shared ``real_redis`` / ``real_redis_client`` fixtures in
``tests/conftest.py``. In CI those share their database with the integration job's live
backend, which the fixtures here keep out of the way.
"""

import socket
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.services import presence


class ManualClock:
    """A clock tests advance explicitly; call it to read epoch seconds."""

    def __init__(self, start: datetime) -> None:
        self.now = start.timestamp()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> ManualClock:
    """Starts 30 s into a UTC minute, mid-day, so tests control every boundary."""
    return ManualClock(datetime(2026, 10, 16, 12, 0, 30, tzinfo=timezone.utc))


@pytest.fixture
def free_tcp_port() -> int:
    """A localhost TCP port the OS just reported free, for a test's ADS-B generator."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def private_presence_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the test its own presence keys, so only the test opens or closes the gate.

    The live backend's broadcast loop republishes ``presence:active_rooms`` (0 when nobody is
    connected) every second into the database the integration job shares with it. The API and
    the ingest both read the key names from ``backend.services.presence``, so renaming them
    there moves every reader and writer in this process to keys that loop never touches.
    """
    suffix = f"test:{uuid4().hex}"
    monkeypatch.setattr(presence, "ACTIVE_ROOMS_KEY", f"{presence.ACTIVE_ROOMS_KEY}:{suffix}")
    monkeypatch.setattr(presence, "LAST_ACTIVITY_KEY", f"{presence.LAST_ACTIVITY_KEY}:{suffix}")

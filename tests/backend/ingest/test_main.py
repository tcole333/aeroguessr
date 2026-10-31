"""Tests for the main ingest loop message handling."""

import asyncio
import dataclasses
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import httpx
import numpy as np
import pytest

# Modules to test
from backend.ingest import main as ingest_main
from backend.ingest.airport_board import AirportBoard, BoardDirection, Route, parse_board_rows
from backend.ingest.parser import RawMessage, parse_sbs_message
from backend.ingest.smoother_enu import PositionSmootherENU
from backend.schemas.plane import PlaneState
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio

# --- Test Fixtures ---


class StubRoutes:
    """In-memory route lookup."""

    def __init__(self, routes: Optional[dict[str, Route]] = None) -> None:
        self.routes = routes or {}

    def lookup(self, callsign: str, now: float) -> Optional[Route]:
        return self.routes.get(callsign)


NO_ROUTES = StubRoutes()


@pytest.fixture(autouse=True)
def clear_global_state() -> None:
    """Clear the global dictionaries before each test."""
    ingest_main.active_smoothers.clear()
    ingest_main.last_timestamps.clear()
    ingest_main.callsign_cache.clear()
    ingest_main.track_cache.clear()
    yield  # Run the test
    ingest_main.active_smoothers.clear()
    ingest_main.last_timestamps.clear()
    ingest_main.callsign_cache.clear()
    ingest_main.track_cache.clear()


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Provides a mock RedisClient with async get/set methods."""
    mock = AsyncMock(spec=RedisClient)
    mock.set_json = AsyncMock()  # Keep for backwards compatibility
    mock.get_model = AsyncMock(return_value=None)  # Default to no existing state
    return mock


@pytest.fixture
def sample_raw_message() -> RawMessage:
    """Provides a sample RawMessage with position data."""
    return RawMessage(
        timestamp=time.time(),
        hex_ident="AC1234",
        msg_type=3,  # Airborne position report
        raw_sbs=(
            "MSG,3,1,1,AC1234,1,2023/01/01,12:00:00.000,"  # Break line
            "2023/01/01,12:00:00.000,,35000,,,42.123,-71.456,,,,"
        ),
        altitude=35000.0,
        latitude=42.123,
        longitude=-71.456,
        squawk=None,
        ground_speed=None,
        track=None,
        vertical_rate=None,
        callsign=None,
    )


def _identification(hex_ident: str, callsign: str, timestamp: float) -> RawMessage:
    return RawMessage(
        timestamp=timestamp, hex_ident=hex_ident, raw_sbs="", msg_type=1, callsign=callsign
    )


# --- Test Cases for handle_message ---


async def test_handle_first_message(
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test processing the first message, including route resolution and trail init."""
    hex_id = sample_raw_message.hex_ident
    initial_pos = np.array(
        [
            sample_raw_message.latitude,
            sample_raw_message.longitude,
            sample_raw_message.altitude,
        ]
    )
    routes = StubRoutes({"TEST1234": Route("KAAA", "KZZZ", "Test Air")})
    ingest_main.callsign_cache[hex_id] = "TEST1234"

    assert hex_id not in ingest_main.active_smoothers
    assert hex_id not in ingest_main.last_timestamps

    await ingest_main.handle_message(sample_raw_message, mock_redis_client, routes=routes)

    # Check smoother was created and timestamp stored
    assert hex_id in ingest_main.active_smoothers
    assert isinstance(ingest_main.active_smoothers[hex_id], PositionSmootherENU)
    assert hex_id in ingest_main.last_timestamps
    assert ingest_main.last_timestamps[hex_id] == sample_raw_message.timestamp

    # Check Redis calls
    mock_redis_client.get_model.assert_called_once_with(f"plane:{hex_id}", PlaneState)
    mock_redis_client.set_json.assert_called_once()
    call_args = mock_redis_client.set_json.call_args

    # Check key
    assert call_args.args[0] == f"plane:{hex_id}"
    # Check model data (initial state, zero velocity, route)
    plane_state: PlaneState = call_args.args[1]
    assert isinstance(plane_state, PlaneState)
    assert plane_state.hex_ident == hex_id
    # The smoother round-trips through ENU coordinates, so compare within float tolerance.
    assert (plane_state.lat, plane_state.lon, plane_state.alt) == pytest.approx(tuple(initial_pos))
    assert plane_state.lat_v == 0.0
    assert plane_state.lon_v == 0.0
    assert plane_state.alt_v == 0.0
    assert plane_state.last_update_ts == sample_raw_message.timestamp
    assert plane_state.callsign == "TEST1234"
    assert plane_state.origin == "KAAA"
    assert plane_state.destination == "KZZZ"

    # Check trail initialization
    assert len(plane_state.trail) == 1
    assert plane_state.trail[0] == pytest.approx(tuple(initial_pos))
    # Check TTL
    assert call_args.kwargs["expire_seconds"] == ingest_main.PLANE_TTL_SECONDS


async def test_handle_subsequent_message(
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test processing a second message, checking trail append and route carry-over."""
    hex_id = sample_raw_message.hex_ident
    initial_pos = (
        sample_raw_message.latitude,
        sample_raw_message.longitude,
        sample_raw_message.altitude,
    )
    routes = StubRoutes({"FIRST": Route("KAAA", "KBBB", None)})
    ingest_main.callsign_cache[hex_id] = "FIRST"

    # --- First message setup ---
    mock_redis_client.get_model.return_value = None  # No state exists initially
    await ingest_main.handle_message(sample_raw_message, mock_redis_client, routes=routes)

    # Get the state that was saved
    saved_state_args = mock_redis_client.set_json.call_args
    first_saved_state: PlaneState = saved_state_args.args[1]

    # Reset mocks for the second call
    mock_redis_client.set_json.reset_mock()
    mock_redis_client.get_model.reset_mock()
    # Mock get_json to return the first saved state for the second call
    mock_redis_client.get_model.return_value = first_saved_state

    assert hex_id in ingest_main.active_smoothers
    smoother = ingest_main.active_smoothers[hex_id]
    smoother.predict = MagicMock()
    smoother.update = MagicMock()
    mock_state_vector = np.array([42.124, -71.457, 35005.0, 0.001, -0.001, 5.0])
    with patch.object(PositionSmootherENU, "state", new_callable=PropertyMock) as mock_prop:
        mock_prop.return_value = mock_state_vector

        # --- Second message ---
        await asyncio.sleep(0.02)
        second_message = dataclasses.replace(
            sample_raw_message,
            timestamp=time.time(),
            latitude=(sample_raw_message.latitude + 0.002),
            longitude=(sample_raw_message.longitude - 0.002),
            altitude=(sample_raw_message.altitude - 10.0),
        )
        new_pos = (
            mock_state_vector[0],
            mock_state_vector[1],
            mock_state_vector[2],
        )

        await ingest_main.handle_message(second_message, mock_redis_client, routes=routes)

        # --- Assertions ---
        # Check smoother predict/update called
        smoother.predict.assert_called_once()
        smoother.update.assert_called_once()

        # Check timestamp updated
        assert ingest_main.last_timestamps[hex_id] == second_message.timestamp

        # Check Redis interaction
        mock_redis_client.get_model.assert_called_once_with(f"plane:{hex_id}", PlaneState)
        mock_redis_client.set_json.assert_called_once()
        call_args = mock_redis_client.set_json.call_args
        second_saved_state: PlaneState = call_args.args[1]

        # Check core data reflects the mocked smoother state
        assert second_saved_state.lat == mock_state_vector[0]
        assert second_saved_state.lon == mock_state_vector[1]
        assert second_saved_state.alt == mock_state_vector[2]
        assert second_saved_state.lat_v == mock_state_vector[3]
        assert second_saved_state.lon_v == mock_state_vector[4]
        assert second_saved_state.alt_v == mock_state_vector[5]
        assert second_saved_state.last_update_ts == second_message.timestamp

        # Check callsign and route carried over from first state
        assert second_saved_state.callsign == "FIRST"
        assert second_saved_state.origin == "KAAA"
        assert second_saved_state.destination == "KBBB"

        # Check trail append
        assert len(second_saved_state.trail) == 2
        assert second_saved_state.trail[0] == initial_pos
        assert second_saved_state.trail[1] == new_pos


async def test_handle_message_missing_position(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
) -> None:
    """Test that messages without position data are skipped."""
    sample_raw_message.latitude = None  # Remove position data

    await ingest_main.handle_message(sample_raw_message, mock_redis_client, routes=NO_ROUTES)

    # Assert no smoother created and no Redis call made
    assert not ingest_main.active_smoothers
    assert not ingest_main.last_timestamps
    mock_redis_client.set_json.assert_not_called()


async def test_handle_message_trail_capping(
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test that the position trail is capped at 10 points."""
    current_state: Optional[PlaneState] = None

    base_time = time.time()
    # Send 11 messages
    for i in range(11):
        # Mock get_json to return the previous state (or None for the first call)
        mock_redis_client.get_model.return_value = current_state
        mock_redis_client.get_model.reset_mock()  # Reset count for each call

        # Create a slightly different message each time
        msg_time = base_time + i * 0.1  # 100ms between messages
        msg = dataclasses.replace(
            sample_raw_message,
            timestamp=msg_time,
            latitude=(sample_raw_message.latitude + i * 0.0001),
            longitude=(sample_raw_message.longitude - i * 0.0001),
            altitude=(sample_raw_message.altitude + i * 1.0),
        )

        # Mock the smoother state property for subsequent messages
        if i > 0:
            mock_state_vector = np.array([msg.latitude, msg.longitude, msg.altitude, 0.0, 0.0, 0.0])
            # Patch the property within a context manager for each iteration > 0
            with patch.object(PositionSmootherENU, "state", new_callable=PropertyMock) as mock_prop:
                mock_prop.return_value = mock_state_vector
                await ingest_main.handle_message(msg, mock_redis_client, routes=NO_ROUTES)
        else:
            # First message doesn't mock smoother state
            await ingest_main.handle_message(msg, mock_redis_client, routes=NO_ROUTES)

        # Store the state that was supposedly saved to Redis for the next iteration
        assert mock_redis_client.set_json.call_count == 1
        saved_args = mock_redis_client.set_json.call_args
        current_state = saved_args.args[1]
        mock_redis_client.set_json.reset_mock()

    # --- Assertions after 11 messages ---
    assert current_state is not None

    # Check trail length is capped
    assert len(current_state.trail) == 10

    # Check the first point (from i=0) is gone
    first_point = (
        sample_raw_message.latitude,
        sample_raw_message.longitude,
        sample_raw_message.altitude,
    )
    assert first_point not in current_state.trail

    # Check the second point (from i=1) IS present (should be the first element now)
    second_point_lat = sample_raw_message.latitude + 1 * 0.0001
    second_point_lon = sample_raw_message.longitude - 1 * 0.0001
    second_point_alt = sample_raw_message.altitude + 1 * 1.0
    assert current_state.trail[0] == pytest.approx(
        (second_point_lat, second_point_lon, second_point_alt)
    )

    # Check the last point (from i=10) is present
    last_point_lat = sample_raw_message.latitude + 10 * 0.0001
    last_point_lon = sample_raw_message.longitude - 10 * 0.0001
    last_point_alt = sample_raw_message.altitude + 10 * 1.0
    assert current_state.trail[-1] == pytest.approx(
        (last_point_lat, last_point_lon, last_point_alt)
    )


async def test_handle_message_kalman_error(
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test handling of LinAlgError during smoother update."""
    hex_id = sample_raw_message.hex_ident

    # --- First message setup ---
    await ingest_main.handle_message(sample_raw_message, mock_redis_client, routes=NO_ROUTES)
    mock_redis_client.set_json.reset_mock()
    assert hex_id in ingest_main.active_smoothers
    smoother = ingest_main.active_smoothers[hex_id]

    # --- Mock smoother update to raise error ---
    smoother.predict = MagicMock()
    smoother.update = MagicMock(side_effect=np.linalg.LinAlgError("Test error"))

    # Mock existing state for graceful recovery
    mock_redis_client.get_model.return_value = None

    # --- Second message ---
    await asyncio.sleep(0.02)
    # Use dataclasses.replace for dataclass objects
    second_message = dataclasses.replace(
        sample_raw_message, timestamp=time.time(), latitude=(sample_raw_message.latitude + 0.002)
    )

    await ingest_main.handle_message(second_message, mock_redis_client, routes=NO_ROUTES)

    # Check smoother was called, resulted in error, and was removed
    smoother.predict.assert_called_once()
    smoother.update.assert_called_once()
    assert hex_id not in ingest_main.active_smoothers
    assert hex_id not in ingest_main.last_timestamps

    # Check Redis was called with raw measurement after error (graceful recovery)
    assert mock_redis_client.set_json.call_count == 1


async def test_handle_message_redis_error(
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test handling of Redis errors during set_json."""
    hex_id = sample_raw_message.hex_ident

    # --- Mock Redis set_json to raise error ---
    mock_redis_client.set_json.side_effect = Exception("Redis unavailable")

    await ingest_main.handle_message(sample_raw_message, mock_redis_client, routes=NO_ROUTES)

    # Check smoother was still created (error happens after smoother logic)
    assert hex_id in ingest_main.active_smoothers
    assert hex_id in ingest_main.last_timestamps

    # Check Redis call was attempted
    mock_redis_client.set_json.assert_called_once()
    # (No further state change expected, error is logged internally)


# --- Route resolution from the local airport board ---


async def test_route_comes_from_the_board_once_the_callsign_is_known(
    redis_client: RedisClient, sample_raw_message: RawMessage
) -> None:
    """MSG,1 carries the callsign; the next position report resolves the route."""
    routes = StubRoutes({"JBU123": Route("KMCO", "KBOS", "JetBlue Airways")})
    hex_id = sample_raw_message.hex_ident

    await ingest_main.handle_message(
        _identification(hex_id, "JBU123  ", sample_raw_message.timestamp - 1),
        redis_client,
        routes=routes,
    )
    await ingest_main.handle_message(sample_raw_message, redis_client, routes=routes)

    stored = await redis_client.get_model(f"plane:{hex_id}", PlaneState)
    assert stored is not None
    assert (stored.callsign, stored.origin, stored.destination, stored.operator) == (
        "JBU123",
        "KMCO",
        "KBOS",
        "JetBlue Airways",
    )


async def test_stored_route_is_kept_when_the_board_forgets_the_flight(
    redis_client: RedisClient, sample_raw_message: RawMessage
) -> None:
    hex_id = sample_raw_message.hex_ident
    ingest_main.callsign_cache[hex_id] = "JBU123"
    board_with_flight = StubRoutes({"JBU123": Route("KMCO", "KBOS", None)})
    await ingest_main.handle_message(sample_raw_message, redis_client, routes=board_with_flight)

    later = dataclasses.replace(sample_raw_message, timestamp=sample_raw_message.timestamp + 1)
    await ingest_main.handle_message(later, redis_client, routes=NO_ROUTES)

    stored = await redis_client.get_model(f"plane:{hex_id}", PlaneState)
    assert stored is not None and stored.origin == "KMCO"


async def test_new_callsign_does_not_inherit_the_old_route(
    redis_client: RedisClient, sample_raw_message: RawMessage
) -> None:
    hex_id = sample_raw_message.hex_ident
    ingest_main.callsign_cache[hex_id] = "JBU123"
    await ingest_main.handle_message(
        sample_raw_message, redis_client, routes=StubRoutes({"JBU123": Route("KMCO", "KBOS", None)})
    )

    ingest_main.callsign_cache[hex_id] = "JBU999"
    later = dataclasses.replace(sample_raw_message, timestamp=sample_raw_message.timestamp + 1)
    await ingest_main.handle_message(later, redis_client, routes=NO_ROUTES)

    stored = await redis_client.get_model(f"plane:{hex_id}", PlaneState)
    assert stored is not None and stored.origin is None and stored.destination is None


async def test_unmatched_plane_for_two_minutes_makes_zero_network_calls(
    redis_client: RedisClient,
) -> None:
    """Regression for #157: one unmatched plane once caused 58 AeroAPI requests in 2 minutes.

    120 s of real SBS traffic (MSG,1 every 5 s, MSG,3 every second) for a plane
    the board does not know must resolve locally and never touch the network.
    """
    now = datetime.now(timezone.utc)
    board = AirportBoard("KBOS")
    board.merge(
        parse_board_rows(
            [
                {
                    "fa_flight_id": "JBU123-1",
                    "ident": "JBU123",
                    "origin": {"code_icao": "KMCO"},
                    "destination": {"code_icao": "KBOS"},
                    "estimated_on": (now + timedelta(minutes=20)).isoformat(),
                }
            ],
            BoardDirection.ARRIVAL,
            "KBOS",
        )
    )
    network_calls: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        network_calls.append(args)
        raise AssertionError("handle_message must not touch the network")

    start = now.timestamp()
    with (
        patch.object(httpx.AsyncClient, "send", side_effect=refuse),
        patch.object(socket.socket, "connect", side_effect=refuse),
    ):
        for second in range(120):
            stamp = datetime.fromtimestamp(start + second, tz=timezone.utc)
            day, clock_time = stamp.strftime("%Y/%m/%d"), stamp.strftime("%H:%M:%S.000")
            lines = []
            if second % 5 == 0:
                lines.append(
                    f"MSG,1,1,1,A1B2C3,1,{day},{clock_time},{day},{clock_time},XYZ999,,,,,,,,,,,"
                )
            lat, lon = 42.5 - second * 0.001, -70.8 - second * 0.001
            lines.append(
                f"MSG,3,1,1,A1B2C3,1,{day},{clock_time},{day},{clock_time},,9000,,,"
                f"{lat:.5f},{lon:.5f},,,0,0,0,0"
            )
            for line in lines:
                msg = parse_sbs_message(line, start + second)
                assert msg is not None
                await ingest_main.handle_message(msg, redis_client, routes=board)

    stored = await redis_client.get_model("plane:A1B2C3", PlaneState)
    assert network_calls == []
    assert stored is not None
    assert stored.callsign == "XYZ999"
    assert stored.origin is None and stored.destination is None

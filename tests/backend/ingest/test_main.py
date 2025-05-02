"""Tests for the main ingest loop message handling."""

import asyncio
import dataclasses
import time
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import numpy as np
import pytest

# Modules to test
from backend.ingest import main as ingest_main
from backend.ingest.enrichment import EnrichedData, RouteData
from backend.ingest.main import PlaneState  # Import PlaneState directly
from backend.ingest.parser import RawMessage
from backend.ingest.smoother import PositionSmoother
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio

# --- Test Fixtures ---


@pytest.fixture(autouse=True)
def clear_global_state() -> None:
    """Clear the global dictionaries before each test."""
    ingest_main.active_smoothers.clear()
    ingest_main.last_timestamps.clear()
    yield  # Run the test
    ingest_main.active_smoothers.clear()
    ingest_main.last_timestamps.clear()


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Provides a mock RedisClient with async get/set methods."""
    mock = AsyncMock(spec=RedisClient)
    mock.set_json = AsyncMock()  # Keep for backwards compatibility
    mock.get_model = AsyncMock(return_value=None)  # Default to no existing state
    mock.get_json = AsyncMock(return_value=None)  # Keep for backwards compatibility
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
        # Other fields are implicitly None if not provided by parser for this msg_type
        # flight_id=None, # Removed - not a field
        squawk=None,
        ground_speed=None,
        track=None,
        vertical_rate=None,
        callsign=None,  # Added callsign explicitly as None for clarity
        # alert=None, # Removed - not a field
        # emergency=None, # Removed - not a field
        # spi=None, # Removed - not a field
        # is_on_ground=None, # Removed - not a field
    )


# --- Test Cases for handle_message ---


@patch("backend.ingest.main.fetch_aeroapi_route", new_callable=AsyncMock)
@patch("backend.ingest.main.fetch_opensky_data", new_callable=AsyncMock)
async def test_handle_first_message(
    mock_fetch_opensky: AsyncMock,
    mock_fetch_aeroapi: AsyncMock,
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test processing the first message, including enrichment fetch and trail init."""
    hex_id = sample_raw_message.hex_ident
    initial_pos = np.array(
        [
            sample_raw_message.latitude,
            sample_raw_message.longitude,
            sample_raw_message.altitude,
        ]
    )

    # Configure mock enrichment data
    sample_opensky_enrichment = EnrichedData(
        callsign="TEST1234", origin_country="Testland", category=3
    )
    sample_aeroapi_route = RouteData(origin_icao="KAAA", destination_icao="KZZZ")
    mock_fetch_opensky.return_value = sample_opensky_enrichment
    mock_fetch_aeroapi.return_value = sample_aeroapi_route

    assert hex_id not in ingest_main.active_smoothers
    assert hex_id not in ingest_main.last_timestamps

    # Ensure Redis get_json returns None for the first message
    mock_redis_client.get_model.return_value = None

    await ingest_main.handle_message(sample_raw_message, mock_redis_client)

    # Check smoother was created and timestamp stored
    assert hex_id in ingest_main.active_smoothers
    assert isinstance(ingest_main.active_smoothers[hex_id], PositionSmoother)
    assert hex_id in ingest_main.last_timestamps
    assert ingest_main.last_timestamps[hex_id] == sample_raw_message.timestamp

    # Check enrichment fetches were called
    mock_fetch_opensky.assert_called_once_with(hex_id, mock_redis_client)
    mock_fetch_aeroapi.assert_called_once_with(hex_id, mock_redis_client)

    # Check Redis calls
    mock_redis_client.get_model.assert_called_once_with(f"plane:{hex_id}", PlaneState)
    mock_redis_client.set_json.assert_called_once()
    call_args = mock_redis_client.set_json.call_args

    # Check key
    assert call_args.args[0] == f"plane:{hex_id}"
    # Check model data (initial state, zero velocity, enrichment)
    plane_state: PlaneState = call_args.args[1]
    assert isinstance(plane_state, ingest_main.PlaneState)
    assert plane_state.hex_ident == hex_id
    assert plane_state.lat == initial_pos[0]
    assert plane_state.lon == initial_pos[1]
    assert plane_state.alt == initial_pos[2]
    assert plane_state.lat_v == 0.0
    assert plane_state.lon_v == 0.0
    assert plane_state.alt_v == 0.0
    assert plane_state.last_update_ts == sample_raw_message.timestamp

    # Check OpenSky enrichment data saved
    assert plane_state.callsign == sample_opensky_enrichment.callsign
    assert plane_state.origin_country == sample_opensky_enrichment.origin_country
    assert plane_state.category == sample_opensky_enrichment.category

    # Check AeroAPI enrichment data saved
    assert plane_state.origin == sample_aeroapi_route.origin_icao
    assert plane_state.destination == sample_aeroapi_route.destination_icao

    # Check trail initialization
    assert len(plane_state.trail) == 1
    assert plane_state.trail[0] == (
        initial_pos[0],
        initial_pos[1],
        initial_pos[2],
    )
    # Check TTL
    assert call_args.kwargs["expire_seconds"] == ingest_main.PLANE_TTL_SECONDS


@patch("backend.ingest.main.fetch_aeroapi_route", new_callable=AsyncMock)
@patch("backend.ingest.main.fetch_opensky_data", new_callable=AsyncMock)
async def test_handle_subsequent_message(
    mock_fetch_opensky: AsyncMock,
    mock_fetch_aeroapi: AsyncMock,
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test processing a second message, checking trail append and enrichment carry-over."""
    hex_id = sample_raw_message.hex_ident
    initial_pos = (
        sample_raw_message.latitude,
        sample_raw_message.longitude,
        sample_raw_message.altitude,
    )

    # --- First message setup ---
    # Configure mock enrichment data for the first call
    sample_opensky_enrichment = EnrichedData(
        callsign="FIRST", origin_country="Initialia", category=1
    )
    sample_aeroapi_route = RouteData(origin_icao="KAAA", destination_icao="KBBB")
    mock_fetch_opensky.return_value = sample_opensky_enrichment
    mock_fetch_aeroapi.return_value = sample_aeroapi_route
    mock_redis_client.get_model.return_value = None  # No state exists initially
    await ingest_main.handle_message(sample_raw_message, mock_redis_client)

    # Check enrichment was fetched on first call
    mock_fetch_opensky.assert_called_once()
    mock_fetch_aeroapi.assert_called_once()
    # Get the state that was saved
    saved_state_args = mock_redis_client.set_json.call_args
    first_saved_state: PlaneState = saved_state_args.args[1]

    # Reset mocks for the second call
    mock_fetch_opensky.reset_mock()
    mock_fetch_aeroapi.reset_mock()
    mock_redis_client.set_json.reset_mock()
    mock_redis_client.get_model.reset_mock()
    # Mock get_json to return the first saved state for the second call
    mock_redis_client.get_model.return_value = first_saved_state

    assert hex_id in ingest_main.active_smoothers
    smoother = ingest_main.active_smoothers[hex_id]
    smoother.predict = MagicMock()
    smoother.update = MagicMock()
    mock_state_vector = np.array([42.124, -71.457, 35005.0, 0.001, -0.001, 5.0])
    with patch.object(PositionSmoother, "state", new_callable=PropertyMock) as mock_prop:
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

        await ingest_main.handle_message(second_message, mock_redis_client)

        # --- Assertions ---
        # Check enrichment was NOT fetched again
        mock_fetch_opensky.assert_not_called()
        mock_fetch_aeroapi.assert_not_called()

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

        # Check OpenSky enrichment data carried over from first state
        assert second_saved_state.callsign == sample_opensky_enrichment.callsign
        assert second_saved_state.origin_country == sample_opensky_enrichment.origin_country
        assert second_saved_state.category == sample_opensky_enrichment.category

        # Check AeroAPI enrichment data carried over from first state
        assert second_saved_state.origin == sample_aeroapi_route.origin_icao
        assert second_saved_state.destination == sample_aeroapi_route.destination_icao

        # Check trail append
        assert len(second_saved_state.trail) == 2
        assert second_saved_state.trail[0] == initial_pos
        assert second_saved_state.trail[1] == new_pos


async def test_handle_message_missing_position(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
) -> None:
    """Test that messages without position data are skipped."""
    sample_raw_message.latitude = None  # Remove position data

    await ingest_main.handle_message(sample_raw_message, mock_redis_client)

    # Assert no smoother created and no Redis call made
    assert not ingest_main.active_smoothers
    assert not ingest_main.last_timestamps
    mock_redis_client.set_json.assert_not_called()


@patch("backend.ingest.main.fetch_aeroapi_route", return_value=None)
@patch("backend.ingest.main.fetch_opensky_data", return_value=None)
async def test_handle_message_trail_capping(
    mock_fetch_opensky: MagicMock,
    mock_fetch_aeroapi: MagicMock,
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test that the position trail is capped at 30 points."""
    # hex_id = sample_raw_message.hex_ident
    current_state: Optional[PlaneState] = None

    # Send 31 messages
    for i in range(31):
        # Mock get_json to return the previous state (or None for the first call)
        mock_redis_client.get_model.return_value = current_state
        mock_redis_client.get_model.reset_mock()  # Reset count for each call

        # Create a slightly different message each time
        msg_time = time.time()
        msg = dataclasses.replace(
            sample_raw_message,
            timestamp=msg_time,
            latitude=(sample_raw_message.latitude + i * 0.0001),
            longitude=(sample_raw_message.longitude - i * 0.0001),
            altitude=(sample_raw_message.altitude + i * 1.0),
        )

        # Mock the smoother state property for subsequent messages
        if i > 0:
            # smoother = ingest_main.active_smoothers[hex_id]
            mock_state_vector = np.array([msg.latitude, msg.longitude, msg.altitude, 0.0, 0.0, 0.0])
            # Patch the property within a context manager for each iteration > 0
            with patch.object(PositionSmoother, "state", new_callable=PropertyMock) as mock_prop:
                mock_prop.return_value = mock_state_vector
                await ingest_main.handle_message(msg, mock_redis_client)
        else:
            # First message doesn't mock smoother state
            await ingest_main.handle_message(msg, mock_redis_client)

        # Store the state that was supposedly saved to Redis for the next iteration
        assert mock_redis_client.set_json.call_count == 1
        saved_args = mock_redis_client.set_json.call_args
        current_state = saved_args.args[1]
        mock_redis_client.set_json.reset_mock()

    # --- Assertions after 31 messages ---
    assert current_state is not None

    # Check trail length is capped
    assert len(current_state.trail) == 30

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

    # Check the last point (from i=30) is present
    last_point_lat = sample_raw_message.latitude + 30 * 0.0001
    last_point_lon = sample_raw_message.longitude - 30 * 0.0001
    last_point_alt = sample_raw_message.altitude + 30 * 1.0
    assert current_state.trail[-1] == pytest.approx(
        (last_point_lat, last_point_lon, last_point_alt)
    )


@patch("backend.ingest.main.fetch_aeroapi_route", return_value=None)
@patch("backend.ingest.main.fetch_opensky_data", return_value=None)
async def test_handle_message_kalman_error(
    mock_fetch_opensky: MagicMock,
    mock_fetch_aeroapi: MagicMock,
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test handling of LinAlgError during smoother update."""
    hex_id = sample_raw_message.hex_ident

    # --- First message setup ---
    await ingest_main.handle_message(sample_raw_message, mock_redis_client)
    mock_redis_client.set_json.reset_mock()
    assert hex_id in ingest_main.active_smoothers
    smoother = ingest_main.active_smoothers[hex_id]

    # --- Mock smoother update to raise error ---
    smoother.predict = MagicMock()
    smoother.update = MagicMock(side_effect=np.linalg.LinAlgError("Test error"))

    # --- Second message ---
    await asyncio.sleep(0.02)
    # Use dataclasses.replace for dataclass objects
    second_message = dataclasses.replace(
        sample_raw_message, timestamp=time.time(), latitude=(sample_raw_message.latitude + 0.002)
    )

    await ingest_main.handle_message(second_message, mock_redis_client)

    # Check smoother was called, resulted in error, and was removed
    smoother.predict.assert_called_once()
    smoother.update.assert_called_once()
    assert hex_id not in ingest_main.active_smoothers
    assert hex_id not in ingest_main.last_timestamps

    # Check no Redis call was made after the error
    mock_redis_client.set_json.assert_not_called()


@patch("backend.ingest.main.fetch_aeroapi_route", return_value=None)
@patch("backend.ingest.main.fetch_opensky_data", return_value=None)
async def test_handle_message_redis_error(
    mock_fetch_opensky: MagicMock,
    mock_fetch_aeroapi: MagicMock,
    mock_redis_client: AsyncMock,
    sample_raw_message: RawMessage,
) -> None:
    """Test handling of Redis errors during set_json."""
    hex_id = sample_raw_message.hex_ident

    # --- Mock Redis set_json to raise error ---
    mock_redis_client.set_json.side_effect = Exception("Redis unavailable")

    await ingest_main.handle_message(sample_raw_message, mock_redis_client)

    # Check smoother was still created (error happens after smoother logic)
    assert hex_id in ingest_main.active_smoothers
    assert hex_id in ingest_main.last_timestamps

    # Check Redis call was attempted
    mock_redis_client.set_json.assert_called_once()
    # (No further state change expected, error is logged internally)

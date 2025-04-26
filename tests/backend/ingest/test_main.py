"""Tests for the main ingest loop message handling."""

import asyncio
import dataclasses
import time
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import numpy as np
import pytest

# Modules to test
from backend.ingest import main as ingest_main
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
    """Provides a mock RedisClient with an async set_json method."""
    mock = AsyncMock(spec=RedisClient)
    mock.set_json = AsyncMock()
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


async def test_handle_first_message(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
) -> None:
    """Test processing the first message for a new aircraft."""
    hex_id = sample_raw_message.hex_ident
    initial_pos = np.array(
        [
            sample_raw_message.latitude,
            sample_raw_message.longitude,
            sample_raw_message.altitude,
        ]
    )

    assert hex_id not in ingest_main.active_smoothers
    assert hex_id not in ingest_main.last_timestamps

    await ingest_main.handle_message(sample_raw_message, mock_redis_client)

    # Check smoother was created and timestamp stored
    assert hex_id in ingest_main.active_smoothers
    assert isinstance(ingest_main.active_smoothers[hex_id], PositionSmoother)
    assert hex_id in ingest_main.last_timestamps
    assert ingest_main.last_timestamps[hex_id] == sample_raw_message.timestamp

    # Check Redis interaction
    mock_redis_client.set_json.assert_called_once()
    call_args = mock_redis_client.set_json.call_args

    # Check key
    assert call_args.args[0] == f"plane:{hex_id}"
    # Check model data (initial state, zero velocity)
    plane_state = call_args.args[1]
    assert isinstance(plane_state, ingest_main.PlaneState)
    assert plane_state.hex_ident == hex_id
    assert plane_state.lat == initial_pos[0]
    assert plane_state.lon == initial_pos[1]
    assert plane_state.alt == initial_pos[2]
    assert plane_state.lat_v == 0.0
    assert plane_state.lon_v == 0.0
    assert plane_state.alt_v == 0.0
    assert plane_state.last_update_ts == sample_raw_message.timestamp
    # Check TTL
    assert call_args.kwargs["expire_seconds"] == ingest_main.PLANE_TTL_SECONDS


async def test_handle_subsequent_message(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
) -> None:
    """Test processing a second message for an existing aircraft."""
    hex_id = sample_raw_message.hex_ident

    # --- First message setup ---
    await ingest_main.handle_message(sample_raw_message, mock_redis_client)
    mock_redis_client.set_json.reset_mock()  # Reset mock after first call
    assert hex_id in ingest_main.active_smoothers
    smoother = ingest_main.active_smoothers[hex_id]
    # Mock the smoother's predict and update methods to check they are called
    smoother.predict = MagicMock()
    smoother.update = MagicMock()
    # Mock the state property getter to return a specific value
    mock_state = np.array([42.124, -71.457, 35005.0, 0.001, -0.001, 5.0])
    with patch.object(PositionSmoother, "state", new_callable=PropertyMock) as mock_prop:
        mock_prop.return_value = mock_state

        # --- Second message ---
        await asyncio.sleep(0.02)  # Ensure dt > 0.01
        # Use dataclasses.replace to create a modified copy
        second_message = dataclasses.replace(
            sample_raw_message,
            timestamp=time.time(),
            latitude=(sample_raw_message.latitude + 0.002),
            longitude=(sample_raw_message.longitude - 0.002),
            altitude=(sample_raw_message.altitude - 10.0),
        )

        # This call must be INSIDE the 'with' block for the mock to apply
        await ingest_main.handle_message(second_message, mock_redis_client)

        # --- Assertions (also inside the with block implicitly) ---
        # Check smoother predict/update were called
        smoother.predict.assert_called_once()
        dt = second_message.timestamp - sample_raw_message.timestamp
        assert smoother.predict.call_args.args[0] == pytest.approx(dt, abs=0.01)
        smoother.update.assert_called_once()
        assert np.allclose(
            smoother.update.call_args.args[0],
            np.array([second_message.latitude, second_message.longitude, second_message.altitude]),
        )

        # Check timestamp updated
        assert ingest_main.last_timestamps[hex_id] == second_message.timestamp

        # Check Redis interaction
        mock_redis_client.set_json.assert_called_once()
        call_args = mock_redis_client.set_json.call_args
        assert call_args.args[0] == f"plane:{hex_id}"
        plane_state = call_args.args[1]
        assert isinstance(plane_state, ingest_main.PlaneState)
        # Check data reflects the mocked smoother state
        assert plane_state.lat == mock_state[0]
        assert plane_state.lon == mock_state[1]
        assert plane_state.alt == mock_state[2]
        assert plane_state.lat_v == mock_state[3]
        assert plane_state.lon_v == mock_state[4]
        assert plane_state.alt_v == mock_state[5]
        assert plane_state.last_update_ts == second_message.timestamp
        assert call_args.kwargs["expire_seconds"] == ingest_main.PLANE_TTL_SECONDS


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


async def test_handle_message_kalman_error(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
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


async def test_handle_message_redis_error(
    mock_redis_client: AsyncMock, sample_raw_message: RawMessage
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

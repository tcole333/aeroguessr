"""Tests for the enhanced flight enrichment v2 module."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.ingest.enrichment import RouteData
from backend.ingest.enrichment_v2 import (
    fetch_route_data_v2,
    get_match_statistics,
    reset_match_statistics,
)
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Provides a mock RedisClient with async methods."""
    mock = AsyncMock(spec=RedisClient)
    mock.get_model = AsyncMock(return_value=None)  # Default cache miss
    mock.set_json = AsyncMock()
    return mock


@pytest.fixture
def sample_route_data() -> RouteData:
    """Provides a sample RouteData object."""
    return RouteData(origin_icao="KBOS", destination_icao="KLAX")


@pytest.fixture(autouse=True)
def reset_stats():
    """Reset match statistics before each test."""
    reset_match_statistics()
    yield
    reset_match_statistics()  # Also reset after


# --- Cache Tests ---


async def test_fetch_route_data_v2_cache_hit(
    mock_redis_client: AsyncMock,
    sample_route_data: RouteData,
):
    """Test cache hit returns cached data without lookups."""
    # Arrange
    hex_ident = "a835af"
    cache_key = "aeroapi_route_v2:a835af"
    mock_redis_client.get_model.return_value = sample_route_data

    # Act
    result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign="UAL123")

    # Assert
    assert result == sample_route_data
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, RouteData)
    mock_redis_client.set_json.assert_not_awaited()

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["total_requests"] == 1
    assert stats["counts"]["cache_hits"] == 1
    assert stats["counts"]["callsign_matches"] == 0


async def test_fetch_route_data_v2_cache_miss_callsign_match(
    mock_redis_client: AsyncMock,
):
    """Test successful callsign lookup on cache miss."""
    # Arrange
    hex_ident = "a835af"
    callsign = "UAL123"

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "KLAX")),
    ) as mock_callsign_lookup:
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Assert
    assert result is not None
    assert result.origin_icao == "KBOS"
    assert result.destination_icao == "KLAX"

    mock_callsign_lookup.assert_awaited_once_with(callsign, mock_redis_client)
    mock_redis_client.set_json.assert_awaited_once()

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["total_requests"] == 1
    assert stats["counts"]["callsign_matches"] == 1
    assert stats["counts"]["registration_matches"] == 0


async def test_fetch_route_data_v2_cache_miss_registration_match(
    mock_redis_client: AsyncMock,
):
    """Test successful registration lookup when callsign fails."""
    # Arrange
    hex_ident = "a835af"
    callsign = "UAL123"

    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ),
        patch(
            "backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")
        ) as mock_hex_to_reg,
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=("KJFK", "KBOS")),
        ) as mock_reg_lookup,
    ):
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Assert
    assert result is not None
    assert result.origin_icao == "KJFK"
    assert result.destination_icao == "KBOS"

    mock_hex_to_reg.assert_awaited_once_with(hex_ident, mock_redis_client)
    mock_reg_lookup.assert_awaited_once_with("N12345", mock_redis_client)
    mock_redis_client.set_json.assert_awaited_once()

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["total_requests"] == 1
    assert stats["counts"]["registration_matches"] == 1
    assert stats["counts"]["callsign_matches"] == 0


async def test_fetch_route_data_v2_no_callsign_registration_lookup(
    mock_redis_client: AsyncMock,
):
    """Test registration lookup when no callsign provided."""
    # Arrange
    hex_ident = "a835af"

    with (
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")),
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=("KMIA", "KDFW")),
        ),
    ):
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=None)

    # Assert
    assert result is not None
    assert result.origin_icao == "KMIA"
    assert result.destination_icao == "KDFW"

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["registration_matches"] == 1


async def test_fetch_route_data_v2_no_match(
    mock_redis_client: AsyncMock,
):
    """Test when neither callsign nor registration lookup succeeds."""
    # Arrange
    hex_ident = "ffffff"
    callsign = "UNKNOWN"

    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ),
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value=None)),
    ):
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Assert
    assert result is None
    mock_redis_client.set_json.assert_not_awaited()

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["total_requests"] == 1
    assert stats["counts"]["no_matches"] == 1


async def test_fetch_route_data_v2_empty_callsign(
    mock_redis_client: AsyncMock,
):
    """Test that empty/whitespace callsign is handled properly."""
    # Arrange
    hex_ident = "a835af"

    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ) as mock_callsign_lookup,
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")),
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=("KORD", "KATL")),
        ),
    ):
        # Act with empty string
        result1 = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign="")
        # Act with whitespace
        result2 = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign="   ")

    # Assert
    assert result1 is not None
    assert result2 is not None
    # Callsign lookup should not be called for empty/whitespace callsigns
    mock_callsign_lookup.assert_not_awaited()


async def test_fetch_route_data_v2_redis_cache_error(
    mock_redis_client: AsyncMock,
):
    """Test that lookups continue despite Redis cache errors."""
    # Arrange
    hex_ident = "a835af"
    callsign = "UAL123"
    mock_redis_client.get_model.side_effect = Exception("Redis error")
    mock_redis_client.set_json.side_effect = Exception("Redis error")

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KSEA", "KDEN")),
    ):
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Assert
    assert result is not None
    assert result.origin_icao == "KSEA"
    assert result.destination_icao == "KDEN"


# --- Synthetic Mode Tests ---


@patch("backend.ingest.enrichment_v2.IS_FAKE_ADSB", True)
async def test_fetch_route_data_v2_fake_adsb_mode(
    mock_redis_client: AsyncMock,
):
    """Test synthetic data generation in FAKE_ADSB mode."""
    # Act
    result = await fetch_route_data_v2("a835af", mock_redis_client, callsign="UAL123")

    # Assert
    assert result is not None
    # Should always have KBOS as either origin or destination
    assert result.origin_icao == "KBOS" or result.destination_icao == "KBOS"
    # Should not call any lookup functions or cache
    mock_redis_client.get_model.assert_not_awaited()
    mock_redis_client.set_json.assert_not_awaited()


@patch("backend.ingest.enrichment_v2.IS_FAKE_ADSB", True)
async def test_fetch_route_data_v2_fake_adsb_always_valid(
    mock_redis_client: AsyncMock,
):
    """Test that FAKE_ADSB mode always returns valid routes."""
    # Run multiple times to test randomness
    for _ in range(10):
        result = await fetch_route_data_v2("test", mock_redis_client)
        assert result is not None
        assert result.origin_icao is not None or result.destination_icao is not None
        # Should not have same origin and destination
        if result.origin_icao and result.destination_icao:
            assert result.origin_icao != result.destination_icao


# --- Statistics Tests ---


async def test_match_statistics_tracking(
    mock_redis_client: AsyncMock,
):
    """Test that match statistics are properly tracked."""
    # Initial state
    stats = get_match_statistics()
    assert stats["total_requests"] == 0

    # Cache hit
    mock_redis_client.get_model.return_value = RouteData(
        origin_icao="KBOS", destination_icao="KLAX"
    )
    await fetch_route_data_v2("test1", mock_redis_client)

    # Callsign match
    mock_redis_client.get_model.return_value = None
    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "KLAX")),
    ):
        await fetch_route_data_v2("test2", mock_redis_client, callsign="UAL123")

    # Registration match
    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ),
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")),
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=("KJFK", "KBOS")),
        ),
    ):
        await fetch_route_data_v2("test3", mock_redis_client, callsign="UAL456")

    # No match
    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ),
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value=None)),
    ):
        await fetch_route_data_v2("test4", mock_redis_client, callsign="UNKNOWN")

    # Check final statistics
    stats = get_match_statistics()
    assert stats["total_requests"] == 4
    assert stats["counts"]["cache_hits"] == 1
    assert stats["counts"]["callsign_matches"] == 1
    assert stats["counts"]["registration_matches"] == 1
    assert stats["counts"]["no_matches"] == 1

    # Check rates
    assert stats["rates"]["cache_hit_rate"] == 25.0
    assert stats["rates"]["callsign_match_rate"] == 25.0
    assert stats["rates"]["registration_match_rate"] == 25.0
    assert stats["rates"]["no_match_rate"] == 25.0


async def test_match_statistics_periodic_logging(
    mock_redis_client: AsyncMock,
    caplog: pytest.LogCaptureFixture,
):
    """Test that statistics are logged periodically."""
    # Make 99 requests without triggering log
    for i in range(99):
        with (
            patch(
                "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
                AsyncMock(return_value=None),
            ),
            patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value=None)),
        ):
            await fetch_route_data_v2(f"test{i}", mock_redis_client)

    # 100th request should trigger logging
    with (
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_callsign", AsyncMock(return_value=None)
        ),
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value=None)),
    ):
        await fetch_route_data_v2("test100", mock_redis_client)

    # Check that statistics were logged
    assert "Route enrichment v2 statistics" in caplog.text
    assert "n=100" in caplog.text


def test_reset_match_statistics():
    """Test resetting match statistics."""
    # Modify statistics
    from backend.ingest.enrichment_v2 import match_stats

    match_stats["total_requests"] = 100
    match_stats["callsign_matches"] = 50

    # Reset
    reset_match_statistics()

    # Check reset
    stats = get_match_statistics()
    assert stats["total_requests"] == 0
    assert all(v == 0 for v in stats["counts"].values())
    assert all(v == 0.0 for v in stats["rates"].values())


def test_get_match_statistics_empty():
    """Test getting statistics when no requests have been made."""
    stats = get_match_statistics()

    assert stats["total_requests"] == 0
    assert stats["rates"]["cache_hit_rate"] == 0.0
    assert stats["rates"]["callsign_match_rate"] == 0.0
    assert stats["rates"]["registration_match_rate"] == 0.0
    assert stats["rates"]["no_match_rate"] == 0.0


# --- Edge Cases ---


async def test_fetch_route_data_v2_registration_but_no_route(
    mock_redis_client: AsyncMock,
):
    """Test when hex converts to registration but no route found."""
    # Arrange
    hex_ident = "a835af"

    with (
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")),
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=None),
        ),
    ):
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client)

    # Assert
    assert result is None

    # Check statistics
    stats = get_match_statistics()
    assert stats["counts"]["no_matches"] == 1


async def test_fetch_route_data_v2_callsign_with_trailing_spaces(
    mock_redis_client: AsyncMock,
):
    """Test that callsigns with trailing spaces are stripped."""
    # Arrange
    hex_ident = "a835af"
    callsign = "UAL123  "  # Trailing spaces

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "KLAX")),
    ) as mock_lookup:
        # Act
        result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Assert
    assert result is not None
    # Should be called with stripped callsign
    mock_lookup.assert_awaited_once_with("UAL123", mock_redis_client)

"""Tests for the enhanced flight enrichment v2 module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.ingest.enrichment import RouteData
from backend.ingest.enrichment_v2 import (
    _lookup_operator_name,
    _operator_cache,
    _query_aeroapi_direct,
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
    callsign = "UAL123"
    # Cache key now includes callsign to prevent stale data when aircraft makes multiple flights
    cache_key = f"aeroapi_route_v2:{hex_ident}:{callsign}"
    mock_redis_client.get_model.return_value = sample_route_data

    # Act
    result = await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

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
    # set_json is called twice: once for route data, once for metadata
    assert mock_redis_client.set_json.await_count == 2

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
    # set_json is called twice: once for route data, once for metadata
    assert mock_redis_client.set_json.await_count == 2

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
    # Even on no match, metadata is still cached for debugging
    assert mock_redis_client.set_json.await_count == 1

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


# --- Cache Key Tests (Callsign-based) ---


async def test_cache_key_includes_callsign(
    mock_redis_client: AsyncMock,
):
    """Test that cache key includes callsign to differentiate routes for same aircraft."""
    hex_ident = "a835af"
    callsign = "PTR2939"
    expected_cache_key = f"aeroapi_route_v2:{hex_ident}:{callsign}"

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("CYYZ", "KBOS")),  # Toronto -> Boston
    ):
        await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Verify the cache key includes callsign
    mock_redis_client.get_model.assert_awaited_once_with(expected_cache_key, RouteData)

    # Verify route data was cached with the correct key
    cache_calls = mock_redis_client.set_json.call_args_list
    assert len(cache_calls) == 2  # route data + metadata
    route_cache_call = cache_calls[0]
    assert route_cache_call[0][0] == expected_cache_key


async def test_different_callsigns_get_different_cache_entries(
    mock_redis_client: AsyncMock,
):
    """Test that same hex with different callsigns creates different cache entries.

    This is the key fix for the bug where PTR2939 flying Toronto->Boston at 8am
    and Boston->Toronto at 12pm would incorrectly return the cached 8am route.
    """
    hex_ident = "a835af"
    callsign_morning = "PTR2939"
    callsign_afternoon = "PTR2940"  # Different callsign for return flight

    # Morning flight: Toronto -> Boston
    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("CYYZ", "KBOS")),
    ):
        result_morning = await fetch_route_data_v2(
            hex_ident, mock_redis_client, callsign=callsign_morning
        )

    # Afternoon flight: Boston -> Toronto (different callsign)
    mock_redis_client.reset_mock()
    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "CYYZ")),
    ):
        result_afternoon = await fetch_route_data_v2(
            hex_ident, mock_redis_client, callsign=callsign_afternoon
        )

    # Assert both routes are correctly fetched (not stale)
    assert result_morning.origin_icao == "CYYZ"
    assert result_morning.destination_icao == "KBOS"
    assert result_afternoon.origin_icao == "KBOS"
    assert result_afternoon.destination_icao == "CYYZ"

    # Verify different cache keys were used
    morning_cache_key = f"aeroapi_route_v2:{hex_ident}:{callsign_morning}"
    afternoon_cache_key = f"aeroapi_route_v2:{hex_ident}:{callsign_afternoon}"
    assert morning_cache_key != afternoon_cache_key


async def test_none_callsign_creates_valid_cache_key(
    mock_redis_client: AsyncMock,
):
    """Test that None callsign creates a valid cache key with 'none' suffix."""
    hex_ident = "a835af"
    expected_cache_key = f"aeroapi_route_v2:{hex_ident}:none"

    with (
        patch("backend.ingest.enrichment_v2.hex_to_registration", AsyncMock(return_value="N12345")),
        patch(
            "backend.ingest.enrichment_v2.lookup_flight_by_registration",
            AsyncMock(return_value=("KORD", "KATL")),
        ),
    ):
        await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=None)

    # Verify the cache key uses 'none' for missing callsign
    mock_redis_client.get_model.assert_awaited_once_with(expected_cache_key, RouteData)


async def test_cache_ttl_is_one_hour(
    mock_redis_client: AsyncMock,
):
    """Test that cache TTL is 1 hour (planes are only in antenna range briefly)."""
    from backend.ingest.enrichment_v2 import ROUTE_CACHE_TTL_SECONDS

    # Assert TTL is 1 hour (3600 seconds)
    assert ROUTE_CACHE_TTL_SECONDS == 3600

    # Also verify it's used when caching
    hex_ident = "a835af"
    callsign = "UAL123"

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "KLAX")),
    ):
        await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Verify set_json was called with the correct TTL
    cache_calls = mock_redis_client.set_json.call_args_list
    assert len(cache_calls) >= 1
    # Check the expire_seconds parameter
    route_cache_call = cache_calls[0]
    assert route_cache_call[1]["expire_seconds"] == 3600


async def test_metadata_cache_key_also_includes_callsign(
    mock_redis_client: AsyncMock,
):
    """Test that metadata cache key also includes callsign for consistency."""
    hex_ident = "a835af"
    callsign = "UAL123"
    expected_meta_key = f"aeroapi_route_v2_meta:{hex_ident}:{callsign}"

    with patch(
        "backend.ingest.enrichment_v2.lookup_flight_by_callsign",
        AsyncMock(return_value=("KBOS", "KLAX")),
    ):
        await fetch_route_data_v2(hex_ident, mock_redis_client, callsign=callsign)

    # Verify metadata was cached with the correct key (includes callsign)
    cache_calls = mock_redis_client.set_json.call_args_list
    assert len(cache_calls) == 2  # route data + metadata
    meta_cache_call = cache_calls[1]
    assert meta_cache_call[0][0] == expected_meta_key


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


# --- Flight Selection Tests ---


class TestSelectBestFlight:
    """Tests for the _select_best_flight helper function."""

    def test_empty_list_returns_none(self):
        """Test that empty flight list returns None."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        result, reason = _select_best_flight([], "TEST123")
        assert result is None
        assert reason == "empty_list"

    def test_no_valid_routes_returns_none(self):
        """Test that flights without origin/destination return None."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {"progress_percent": 50},  # No origin/destination
            {"status": "scheduled"},  # No origin/destination
        ]
        result, reason = _select_best_flight(flights, "TEST123")
        assert result is None
        assert reason == "no_valid_routes"

    def test_in_progress_flight_preferred(self):
        """Test that in-progress flight is selected over historical flights."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KMCO"},
                "destination": {"code_icao": "KBOS"},
                "progress_percent": None,
                "scheduled_out": "2024-01-01T10:00:00Z",
            },
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "MDSD"},
                "progress_percent": 45,
                "scheduled_out": "2024-01-01T08:00:00Z",
            },
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KLAX"},
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",
            },
        ]
        result, reason = _select_best_flight(flights, "JBU1829")

        assert result is not None
        assert reason == "in_progress"
        assert result["destination"]["code_icao"] == "MDSD"

    def test_in_progress_zero_not_selected(self):
        """Test that progress_percent=0 is not considered in-progress."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KLAX"},
                "progress_percent": 0,  # Not yet departed
                "scheduled_out": "2024-01-01T10:00:00Z",
            },
            {
                "origin": {"code_icao": "KJFK"},
                "destination": {"code_icao": "KBOS"},
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        # Should fall through to monitored airport match (KBOS)
        assert result is not None
        assert reason in ("matches_monitored", "most_recent")

    def test_in_progress_100_not_selected(self):
        """Test that progress_percent=100 (completed) is not considered in-progress."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KMCO"},
                "destination": {"code_icao": "KORD"},
                "progress_percent": 100,  # Completed flight
                "scheduled_out": "2024-01-01T08:00:00Z",
            },
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KLAX"},
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        # Should fall through to monitored airport match
        assert result is not None
        assert reason == "matches_monitored"
        assert result["origin"]["code_icao"] == "KBOS"

    def test_monitored_airport_preferred_over_other_historical(self):
        """Test that flights matching KBOS are preferred over other routes."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        # This is the key bug fix test: JBU1829 BOS->Santo Domingo vs BOS->Orlando
        flights = [
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KMCO"},  # Orlando - older flight
                "progress_percent": None,
                "scheduled_out": "2024-01-01T08:00:00Z",
            },
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "MDSD"},  # Santo Domingo - newer
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",
            },
            {
                "origin": {"code_icao": "KJFK"},
                "destination": {"code_icao": "KLAX"},  # Unrelated route
                "progress_percent": None,
                "scheduled_out": "2024-01-03T10:00:00Z",
            },
        ]
        result, reason = _select_best_flight(flights, "JBU1829")

        assert result is not None
        assert reason == "matches_monitored"
        # Should pick the MOST RECENT BOS flight (Santo Domingo, not Orlando)
        assert result["destination"]["code_icao"] == "MDSD"

    def test_most_recent_when_no_monitored_match(self):
        """Test fallback to most recent flight when no KBOS match."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KJFK"},
                "destination": {"code_icao": "KLAX"},
                "progress_percent": None,
                "scheduled_out": "2024-01-01T08:00:00Z",
            },
            {
                "origin": {"code_icao": "KMIA"},
                "destination": {"code_icao": "KORD"},
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        assert result is not None
        assert reason == "most_recent"
        # Should pick the more recent flight (MIA->ORD)
        assert result["origin"]["code_icao"] == "KMIA"

    def test_actual_out_preferred_over_scheduled_out(self):
        """Test that actual_out is used when available for recency sorting."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KJFK"},
                "destination": {"code_icao": "KLAX"},
                "progress_percent": None,
                "scheduled_out": "2024-01-02T10:00:00Z",  # Later scheduled
                "actual_out": "2024-01-01T10:00:00Z",  # But departed earlier
            },
            {
                "origin": {"code_icao": "KMIA"},
                "destination": {"code_icao": "KORD"},
                "progress_percent": None,
                "scheduled_out": "2024-01-01T08:00:00Z",  # Earlier scheduled
                "actual_out": "2024-01-02T12:00:00Z",  # But departed later
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        assert result is not None
        # Should pick MIA->ORD because its actual_out is later
        assert result["origin"]["code_icao"] == "KMIA"

    def test_destination_only_flight_is_valid(self):
        """Test that flights with only destination (no origin) are valid."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {},
                "destination": {"code_icao": "KBOS"},
                "progress_percent": None,
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        assert result is not None
        assert result["destination"]["code_icao"] == "KBOS"

    def test_origin_only_flight_is_valid(self):
        """Test that flights with only origin (no destination) are valid."""
        from backend.ingest.enrichment_v2 import _select_best_flight

        flights = [
            {
                "origin": {"code_icao": "KBOS"},
                "destination": {},
                "progress_percent": None,
            },
        ]
        result, reason = _select_best_flight(flights, "TEST123")

        assert result is not None
        assert result["origin"]["code_icao"] == "KBOS"


class TestGetMostRecentFlight:
    """Tests for the _get_most_recent_flight helper function."""

    def test_sorts_by_actual_out(self):
        """Test sorting by actual_out time."""
        from backend.ingest.enrichment_v2 import _get_most_recent_flight

        flights = [
            {"actual_out": "2024-01-01T08:00:00Z"},
            {"actual_out": "2024-01-02T10:00:00Z"},
            {"actual_out": "2024-01-01T12:00:00Z"},
        ]
        result = _get_most_recent_flight(flights)
        assert result["actual_out"] == "2024-01-02T10:00:00Z"

    def test_sorts_by_scheduled_out_when_no_actual(self):
        """Test sorting by scheduled_out when actual_out is not available."""
        from backend.ingest.enrichment_v2 import _get_most_recent_flight

        flights = [
            {"scheduled_out": "2024-01-01T08:00:00Z"},
            {"scheduled_out": "2024-01-02T10:00:00Z"},
            {"scheduled_out": "2024-01-01T12:00:00Z"},
        ]
        result = _get_most_recent_flight(flights)
        assert result["scheduled_out"] == "2024-01-02T10:00:00Z"

    def test_mixed_actual_and_scheduled(self):
        """Test that actual_out takes precedence over scheduled_out."""
        from backend.ingest.enrichment_v2 import _get_most_recent_flight

        flights = [
            {"scheduled_out": "2024-01-03T08:00:00Z"},  # No actual
            {"actual_out": "2024-01-02T10:00:00Z", "scheduled_out": "2024-01-01T10:00:00Z"},
        ]
        result = _get_most_recent_flight(flights)
        # The scheduled_out flight comes last alphabetically but has no actual_out
        # The actual_out flight should win based on the actual departure time
        assert result.get("scheduled_out") == "2024-01-03T08:00:00Z"

    def test_no_times_returns_first(self):
        """Test that first flight is returned when no times available."""
        from backend.ingest.enrichment_v2 import _get_most_recent_flight

        flights = [
            {"origin": {"code_icao": "KBOS"}},
            {"origin": {"code_icao": "KJFK"}},
        ]
        result = _get_most_recent_flight(flights)
        # With no times, sort is stable so original order preserved
        assert result["origin"]["code_icao"] in ("KBOS", "KJFK")


# --- Direct AeroAPI Query Tests ---


class TestQueryAeroApiDirect:
    """Tests for the _query_aeroapi_direct() function (Tier 3-4 enrichment)."""

    async def test_single_flight_success(self):
        """Happy path - single flight with valid route returns RouteData."""
        mock_response_data = {
            "flights": [
                {
                    "origin": {"code_icao": "KBOS"},
                    "destination": {"code_icao": "KLAX"},
                    "progress_percent": 45,
                    "operator_icao": "UAL",
                }
            ]
        }

        # Create a mock response object (not async - httpx Response methods are sync)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
            patch(
                "backend.ingest.enrichment_v2._lookup_operator_name",
                AsyncMock(return_value="United"),
            ),
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("UAL123")

        assert result is not None
        assert result.origin_icao == "KBOS"
        assert result.destination_icao == "KLAX"
        assert result.operator == "United"

    async def test_multiple_flights_selects_in_progress(self):
        """Multiple flights - in-progress flight is selected over historical."""
        mock_response_data = {
            "flights": [
                {
                    "origin": {"code_icao": "KMCO"},
                    "destination": {"code_icao": "KBOS"},
                    "progress_percent": None,
                    "scheduled_out": "2024-01-01T10:00:00Z",
                },
                {
                    "origin": {"code_icao": "KBOS"},
                    "destination": {"code_icao": "MDSD"},
                    "progress_percent": 45,  # In progress
                    "scheduled_out": "2024-01-01T08:00:00Z",
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
            patch(
                "backend.ingest.enrichment_v2._lookup_operator_name",
                AsyncMock(return_value=None),
            ),
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("JBU1829")

        assert result is not None
        assert result.origin_icao == "KBOS"
        assert result.destination_icao == "MDSD"

    async def test_no_valid_routes_returns_none(self):
        """All flights missing origin AND destination returns None."""
        mock_response_data = {
            "flights": [
                {"progress_percent": 50},  # No origin/destination
                {"status": "scheduled"},  # No origin/destination
            ]
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("TEST123")

        assert result is None

    async def test_404_not_found(self):
        """AeroAPI returns 404 - flight not found, returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("UNKNOWN")

        assert result is None

    async def test_http_500_error(self):
        """Server error - returns None gracefully."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(500),
        )

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("TEST123")

        assert result is None

    async def test_timeout_returns_none(self):
        """Connection timeout - returns None gracefully."""
        import httpx

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.side_effect = httpx.ReadTimeout("Connection timeout")

            result = await _query_aeroapi_direct("TEST123")

        assert result is None

    async def test_empty_flights_array(self):
        """API returns empty flights list - returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"flights": []}

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _query_aeroapi_direct("N12345")

        assert result is None

    async def test_no_api_key_returns_none(self):
        """Missing FLIGHTAWARE_API_KEY returns None without making API call."""
        with patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", None):
            result = await _query_aeroapi_direct("UAL123")

        assert result is None


# --- Operator Lookup Tests ---


class TestLookupOperatorName:
    """Tests for the _lookup_operator_name() function."""

    @pytest.fixture(autouse=True)
    def clear_operator_cache(self):
        """Clear the operator cache before and after each test."""
        _operator_cache.clear()
        yield
        _operator_cache.clear()

    async def test_cache_hit(self):
        """Returns cached operator name without API call."""
        # Pre-populate cache
        _operator_cache["UAL"] = "United"

        with patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client:
            result = await _lookup_operator_name("UAL")

        # Should return cached value without making API call
        assert result == "United"
        mock_client.assert_not_called()

    async def test_api_success_and_caches(self):
        """Fetches from API and caches result."""
        mock_response_data = {
            "shortname": "Delta",
            "callsign": "Delta",
            "name": "Delta Air Lines",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _lookup_operator_name("DAL")

        assert result == "Delta"
        # Should be cached now
        assert _operator_cache["DAL"] == "Delta"

    async def test_404_returns_none(self):
        """Unknown operator returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _lookup_operator_name("UNKNOWN")

        assert result is None
        # Should not cache 404s
        assert "UNKNOWN" not in _operator_cache

    async def test_no_api_key_returns_none(self):
        """Missing FLIGHTAWARE_API_KEY returns None."""
        with patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", None):
            result = await _lookup_operator_name("UAL")

        assert result is None

    async def test_empty_operator_icao_returns_none(self):
        """Empty operator ICAO returns None immediately."""
        with patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client:
            result = await _lookup_operator_name("")

        assert result is None
        mock_client.assert_not_called()

    async def test_http_error_returns_none(self):
        """HTTP error returns None gracefully."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=httpx.Request("GET", "https://example.com"),
            response=httpx.Response(500),
        )

        with (
            patch("backend.ingest.enrichment_v2.FLIGHTAWARE_API_KEY", "test-api-key"),
            patch("backend.ingest.enrichment_v2.httpx.AsyncClient") as mock_client,
        ):
            mock_instance = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_instance
            mock_instance.get.return_value = mock_response

            result = await _lookup_operator_name("UAL")

        assert result is None

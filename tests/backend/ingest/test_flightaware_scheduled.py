"""Tests for the FlightAware scheduled flights module."""

from datetime import datetime, timedelta
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.ingest.flightaware_scheduled import (
    FlightAwareScheduledClient,
    FlightScheduleCache,
    ScheduledFlight,
    build_flight_schedule_cache,
    lookup_flight_by_callsign,
    lookup_flight_by_registration,
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
def sample_departure_flight() -> ScheduledFlight:
    """Provides a sample scheduled departure flight."""
    return ScheduledFlight(
        ident="UAL123",
        registration="N12345",
        origin_icao="KBOS",
        destination_icao="KLAX",
        scheduled_departure=datetime.utcnow() + timedelta(hours=1),
        scheduled_arrival=datetime.utcnow() + timedelta(hours=6),
        aircraft_type="B738",
    )


@pytest.fixture
def sample_arrival_flight() -> ScheduledFlight:
    """Provides a sample scheduled arrival flight."""
    return ScheduledFlight(
        ident="DAL456",
        registration="N67890",
        origin_icao="KJFK",
        destination_icao="KBOS",
        scheduled_departure=datetime.utcnow() - timedelta(hours=2),
        scheduled_arrival=datetime.utcnow() + timedelta(hours=1),
        aircraft_type="A320",
    )


@pytest.fixture
def sample_schedule_cache(
    sample_departure_flight: ScheduledFlight,
    sample_arrival_flight: ScheduledFlight,
) -> FlightScheduleCache:
    """Provides a sample flight schedule cache."""
    return FlightScheduleCache(
        last_updated=datetime.utcnow(),
        departures=[sample_departure_flight],
        arrivals=[sample_arrival_flight],
        callsign_lookup={
            "UAL123": sample_departure_flight,
            "DAL456": sample_arrival_flight,
        },
        registration_lookup={
            "N12345": sample_departure_flight,
            "N67890": sample_arrival_flight,
        },
    )


@pytest.fixture
def sample_api_departure_response() -> Dict:
    """Provides a sample FlightAware scheduled departures API response."""
    return {
        "scheduled_departures": [
            {
                "ident": "UAL123",
                "registration": "N12345",
                "origin": {
                    "code": "BOS",
                    "code_icao": "KBOS",
                    "code_iata": "BOS",
                },
                "destination": {
                    "code": "LAX",
                    "code_icao": "KLAX",
                    "code_iata": "LAX",
                },
                "scheduled_off": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
                "scheduled_on": (datetime.utcnow() + timedelta(hours=6)).isoformat() + "Z",
                "aircraft_type": "B738",
            },
            {
                "ident": "AAL789",
                "registration": None,  # Missing registration
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KMIA"},
                "scheduled_off": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
                "scheduled_on": (datetime.utcnow() + timedelta(hours=5)).isoformat() + "Z",
                "aircraft_type": "B737",
            },
        ]
    }


@pytest.fixture
def sample_api_arrival_response() -> Dict:
    """Provides a sample FlightAware scheduled arrivals API response."""
    return {
        "scheduled_arrivals": [
            {
                "ident": "DAL456",
                "registration": "N67890",
                "origin": {
                    "code": "JFK",
                    "code_icao": "KJFK",
                    "code_iata": "JFK",
                },
                "destination": {
                    "code": "BOS",
                    "code_icao": "KBOS",
                    "code_iata": "BOS",
                },
                "scheduled_off": (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z",
                "scheduled_on": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z",
                "aircraft_type": "A320",
            }
        ]
    }


# --- FlightAwareScheduledClient Tests ---


def test_client_init_with_api_key():
    """Test client initialization with API key."""
    client = FlightAwareScheduledClient(api_key="test-key-123")
    assert client.api_key == "test-key-123"
    assert client.headers == {"x-apikey": "test-key-123"}


def test_client_init_from_env():
    """Test client initialization from environment variable."""
    with patch("backend.ingest.flightaware_scheduled.FLIGHTAWARE_API_KEY", "env-key"):
        client = FlightAwareScheduledClient()
        assert client.api_key == "env-key"
        assert client.headers == {"x-apikey": "env-key"}


def test_client_init_no_api_key():
    """Test client initialization without API key."""
    with patch("backend.ingest.flightaware_scheduled.FLIGHTAWARE_API_KEY", None):
        client = FlightAwareScheduledClient()
        assert client.api_key is None
        assert client.headers == {}


@patch("httpx.AsyncClient")
async def test_fetch_scheduled_departures_success(
    mock_async_client_cls: MagicMock,
    sample_api_departure_response: Dict,
):
    """Test successful fetch of scheduled departures."""
    # Arrange
    client = FlightAwareScheduledClient(api_key="test-key")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_api_departure_response

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    flights = await client.fetch_scheduled_departures("KBOS", max_pages=2)

    # Assert
    assert len(flights) == 2
    assert flights[0].ident == "UAL123"
    assert flights[0].registration == "N12345"
    assert flights[0].origin_icao == "KBOS"
    assert flights[0].destination_icao == "KLAX"
    assert flights[1].ident == "AAL789"
    assert flights[1].registration is None  # Should handle missing registration


async def test_fetch_scheduled_departures_no_api_key():
    """Test fetch departures without API key returns empty list."""
    client = FlightAwareScheduledClient(api_key=None)
    flights = await client.fetch_scheduled_departures("KBOS")
    assert flights == []


@patch("httpx.AsyncClient")
async def test_fetch_scheduled_departures_api_error(
    mock_async_client_cls: MagicMock,
):
    """Test handling of API errors when fetching departures."""
    # Arrange
    client = FlightAwareScheduledClient(api_key="test-key")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    http_error = httpx.HTTPStatusError(
        message="Client error '401 Unauthorized'",
        request=MagicMock(),
        response=mock_response,
    )
    mock_response.raise_for_status = MagicMock(side_effect=http_error)

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    flights = await client.fetch_scheduled_departures("KBOS")

    # Assert
    assert flights == []


@patch("httpx.AsyncClient")
async def test_fetch_scheduled_departures_connection_error(
    mock_async_client_cls: MagicMock,
):
    """Test handling of connection errors when fetching departures."""
    # Arrange
    client = FlightAwareScheduledClient(api_key="test-key")

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    flights = await client.fetch_scheduled_departures("KBOS")

    # Assert
    assert flights == []


@patch("httpx.AsyncClient")
async def test_fetch_scheduled_departures_malformed_data(
    mock_async_client_cls: MagicMock,
):
    """Test handling of malformed flight data in API response."""
    # Arrange
    client = FlightAwareScheduledClient(api_key="test-key")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "scheduled_departures": [
            {
                # Missing required fields
                "some_field": "value",
            },
            {
                "ident": "VALID123",
                "origin": {"code_icao": "KBOS"},
                "destination": {"code_icao": "KJFK"},
            },
        ]
    }

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    flights = await client.fetch_scheduled_departures("KBOS")

    # Assert
    assert len(flights) == 2  # Both flights parsed (even with empty ident)
    assert flights[0].ident == ""  # Empty string for missing ident
    assert flights[1].ident == "VALID123"


@patch("httpx.AsyncClient")
async def test_fetch_scheduled_arrivals_success(
    mock_async_client_cls: MagicMock,
    sample_api_arrival_response: Dict,
):
    """Test successful fetch of scheduled arrivals."""
    # Arrange
    client = FlightAwareScheduledClient(api_key="test-key")

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_api_arrival_response

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    flights = await client.fetch_scheduled_arrivals("KBOS", max_pages=1)

    # Assert
    assert len(flights) == 1
    assert flights[0].ident == "DAL456"
    assert flights[0].registration == "N67890"
    assert flights[0].origin_icao == "KJFK"
    assert flights[0].destination_icao == "KBOS"


async def test_fetch_scheduled_arrivals_no_api_key():
    """Test fetch arrivals without API key returns empty list."""
    client = FlightAwareScheduledClient(api_key=None)
    flights = await client.fetch_scheduled_arrivals("KBOS")
    assert flights == []


# --- build_flight_schedule_cache Tests ---


async def test_build_flight_schedule_cache_fresh(
    mock_redis_client: AsyncMock,
    sample_api_departure_response: Dict,
    sample_api_arrival_response: Dict,
):
    """Test building fresh flight schedule cache."""
    # Arrange
    mock_redis_client.get_model.return_value = None  # No cache

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.fetch_scheduled_departures = AsyncMock(
            return_value=[
                ScheduledFlight(
                    ident="UAL123",
                    registration="N12345",
                    origin_icao="KBOS",
                    destination_icao="KLAX",
                )
            ]
        )
        mock_client.fetch_scheduled_arrivals = AsyncMock(
            return_value=[
                ScheduledFlight(
                    ident="DAL456",
                    registration="N67890",
                    origin_icao="KJFK",
                    destination_icao="KBOS",
                )
            ]
        )
        mock_client_cls.return_value = mock_client

        # Act
        cache = await build_flight_schedule_cache(mock_redis_client, force_refresh=False)

    # Assert
    assert cache is not None
    assert len(cache.departures) == 1
    assert len(cache.arrivals) == 1
    assert "UAL123" in cache.callsign_lookup
    assert "DAL456" in cache.callsign_lookup
    assert "N12345" in cache.registration_lookup
    assert "N67890" in cache.registration_lookup
    mock_redis_client.set_json.assert_awaited_once()


async def test_build_flight_schedule_cache_hit(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test using cached flight schedule."""
    # Arrange
    mock_redis_client.get_model.return_value = sample_schedule_cache

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        # Act
        cache = await build_flight_schedule_cache(mock_redis_client, force_refresh=False)

    # Assert
    assert cache == sample_schedule_cache
    mock_client_cls.assert_not_called()  # Should not create API client
    mock_redis_client.set_json.assert_not_awaited()  # Should not update cache


async def test_build_flight_schedule_cache_stale(
    mock_redis_client: AsyncMock,
):
    """Test rebuilding stale cache."""
    # Arrange
    stale_cache = FlightScheduleCache(
        last_updated=datetime.utcnow() - timedelta(hours=13),  # Over 12 hours old
        departures=[],
        arrivals=[],
        callsign_lookup={},
        registration_lookup={},
    )
    mock_redis_client.get_model.return_value = stale_cache

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.fetch_scheduled_departures = AsyncMock(return_value=[])
        mock_client.fetch_scheduled_arrivals = AsyncMock(return_value=[])
        mock_client_cls.return_value = mock_client

        # Act
        cache = await build_flight_schedule_cache(mock_redis_client, force_refresh=False)

    # Assert
    assert cache is not None
    assert cache != stale_cache  # Should be new cache
    mock_client.fetch_scheduled_departures.assert_awaited_once()
    mock_client.fetch_scheduled_arrivals.assert_awaited_once()


async def test_build_flight_schedule_cache_force_refresh(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test force refresh bypasses cache."""
    # Arrange
    mock_redis_client.get_model.return_value = sample_schedule_cache

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.fetch_scheduled_departures = AsyncMock(return_value=[])
        mock_client.fetch_scheduled_arrivals = AsyncMock(return_value=[])
        mock_client_cls.return_value = mock_client

        # Act
        await build_flight_schedule_cache(mock_redis_client, force_refresh=True)

    # Assert
    mock_redis_client.get_model.assert_not_awaited()  # Should skip cache check
    mock_client.fetch_scheduled_departures.assert_awaited_once()
    mock_client.fetch_scheduled_arrivals.assert_awaited_once()


async def test_build_flight_schedule_cache_redis_error(
    mock_redis_client: AsyncMock,
):
    """Test cache building continues despite Redis errors."""
    # Arrange
    mock_redis_client.get_model.side_effect = Exception("Redis error")
    mock_redis_client.set_json.side_effect = Exception("Redis error")

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.fetch_scheduled_departures = AsyncMock(
            return_value=[
                ScheduledFlight(
                    ident="UAL123",
                    registration="N12345",
                    origin_icao="KBOS",
                    destination_icao="KLAX",
                )
            ]
        )
        mock_client.fetch_scheduled_arrivals = AsyncMock(return_value=[])
        mock_client_cls.return_value = mock_client

        # Act
        cache = await build_flight_schedule_cache(mock_redis_client)

    # Assert
    assert cache is not None
    assert "UAL123" in cache.callsign_lookup


async def test_build_flight_schedule_cache_duplicate_handling(
    mock_redis_client: AsyncMock,
):
    """Test handling of duplicate flights in departures/arrivals."""
    # Arrange
    duplicate_flight = ScheduledFlight(
        ident="DUP123",
        registration="N99999",
        origin_icao="KBOS",
        destination_icao="KLAX",
    )

    with patch(
        "backend.ingest.flightaware_scheduled.FlightAwareScheduledClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.fetch_scheduled_departures = AsyncMock(return_value=[duplicate_flight])
        mock_client.fetch_scheduled_arrivals = AsyncMock(return_value=[duplicate_flight])
        mock_client_cls.return_value = mock_client

        # Act
        cache = await build_flight_schedule_cache(mock_redis_client)

    # Assert
    assert len(cache.callsign_lookup) == 1  # Should not duplicate
    assert len(cache.registration_lookup) == 1
    assert cache.callsign_lookup["DUP123"] == duplicate_flight


# --- Lookup Function Tests ---


async def test_lookup_flight_by_callsign_found(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test successful callsign lookup."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=sample_schedule_cache),
    ):
        # Act
        result = await lookup_flight_by_callsign("UAL123", mock_redis_client)

    # Assert
    assert result == ("KBOS", "KLAX")


async def test_lookup_flight_by_callsign_not_found(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test callsign lookup with no match."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=sample_schedule_cache),
    ):
        # Act
        result = await lookup_flight_by_callsign("NOTFOUND", mock_redis_client)

    # Assert
    assert result is None


async def test_lookup_flight_by_callsign_no_cache(
    mock_redis_client: AsyncMock,
):
    """Test callsign lookup when cache building fails."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=None),
    ):
        # Act
        result = await lookup_flight_by_callsign("UAL123", mock_redis_client)

    # Assert
    assert result is None


async def test_lookup_flight_by_registration_found(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test successful registration lookup."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=sample_schedule_cache),
    ):
        # Act
        result = await lookup_flight_by_registration("N67890", mock_redis_client)

    # Assert
    assert result == ("KJFK", "KBOS")


async def test_lookup_flight_by_registration_not_found(
    mock_redis_client: AsyncMock,
    sample_schedule_cache: FlightScheduleCache,
):
    """Test registration lookup with no match."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=sample_schedule_cache),
    ):
        # Act
        result = await lookup_flight_by_registration("N00000", mock_redis_client)

    # Assert
    assert result is None


async def test_lookup_flight_by_registration_no_cache(
    mock_redis_client: AsyncMock,
):
    """Test registration lookup when cache building fails."""
    # Arrange
    with patch(
        "backend.ingest.flightaware_scheduled.build_flight_schedule_cache",
        AsyncMock(return_value=None),
    ):
        # Act
        result = await lookup_flight_by_registration("N12345", mock_redis_client)

    # Assert
    assert result is None

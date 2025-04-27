"""Tests for the OpenSky enrichment logic."""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import redis

# Module to test
from backend.ingest import enrichment as enrichment_module
from backend.ingest.enrichment import (
    EnrichedData,
    RouteData,
    fetch_aeroapi_route,
    fetch_opensky_data,
)
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio

# --- Test Fixtures ---


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Provides a mock RedisClient with async get/set methods."""
    mock = AsyncMock(spec=RedisClient)
    # Mock get_model to return None by default (cache miss)
    mock.get_model = AsyncMock(return_value=None)
    mock.set_json = AsyncMock()
    return mock


@pytest.fixture
def sample_enriched_data() -> EnrichedData:
    """Provides a sample EnrichedData object."""
    return EnrichedData(callsign="SWA123", origin_country="United States", category=3)


@pytest.fixture
def sample_opensky_response_vector() -> list:
    """Provides a sample OpenSky state vector array (as returned in API)."""
    # Based on OpenSky REST API documentation, matching expected fields
    return [
        "a835af",  # 0: icao24
        "SWA123  ",  # 1: callsign (note trailing spaces)
        "United States",  # 2: origin_country
        1678886400,  # 3: time_position
        1678886401,  # 4: last_contact
        -97.0403,  # 5: longitude
        32.8968,  # 6: latitude
        7000.0,  # 7: baro_altitude (meters)
        False,  # 8: on_ground
        200.0,  # 9: velocity (m/s)
        180.0,  # 10: true_track
        5.0,  # 11: vertical_rate
        None,  # 12: sensors (int array)
        7100.0,  # 13: geo_altitude
        "7340",  # 14: squawk
        False,  # 15: spi
        0,  # 16: position_source (ADS-B)
        3,  # 17: category (Small)
    ]


@pytest.fixture
def sample_route_data() -> RouteData:
    """Provides a sample RouteData object."""
    return RouteData(origin_icao="KSFO", destination_icao="KJFK")


@pytest.fixture
def sample_aeroapi_flights_response() -> Dict[str, Any]:
    """Provides a sample successful AeroAPI /flights/{id} response."""
    return {
        "flights": [
            {
                "ident": "SWA123",
                "ident_icao": "SWA123",
                "ident_iata": "WN123",
                "fa_flight_id": "SWA123-1678886400-airline-0123",
                "operator": "SWA",
                "operator_icao": "SWA",
                "operator_iata": "WN",
                "flight_number": "123",
                "registration": "N123SW",
                "atc_ident": None,
                "inbound_fa_flight_id": "DAL456-1678886400-airline-0456",
                "blocked": False,
                "diverted": False,
                "cancelled": False,
                "position_only": False,
                "origin": {
                    "code": "KSFO",
                    "code_icao": "KSFO",
                    "code_iata": "SFO",
                    "code_lid": None,
                    "airport_info_url": "/airports/KSFO",
                },
                "destination": {
                    "code": "KJFK",
                    "code_icao": "KJFK",
                    "code_iata": "JFK",
                    "code_lid": None,
                    "airport_info_url": "/airports/KJFK",
                },
                "departure_delay": 0,
                "arrival_delay": 0,
                "filed_ete": 18000,
                "progress_percent": 50,
                "status": "En Route / Landing",
                "aircraft_type": "B738",
                "route_distance": 2586,
                "filed_airspeed": 450,
                "filed_altitude": 350,
                "filed_route": "...",
                "actual_route": "...",
                "scheduled_out": "2023-03-15T10:00:00Z",
                "estimated_out": "2023-03-15T10:00:00Z",
                "actual_out": "2023-03-15T10:05:00Z",
                "scheduled_off": "2023-03-15T10:10:00Z",
                "estimated_off": "2023-03-15T10:10:00Z",
                "actual_off": "2023-03-15T10:15:00Z",
                "scheduled_on": "2023-03-15T18:00:00Z",
                "estimated_on": "2023-03-15T18:05:00Z",
                "actual_on": None,
                "scheduled_in": "2023-03-15T18:10:00Z",
                "estimated_in": "2023-03-15T18:15:00Z",
                "actual_in": None,
                "foresight_predictions_available": True,
                # Add other fields as needed for testing
            }
            # Potentially more flights if the ident matches multiple
        ],
        "links": {"next": "/flights/a835af?cursor=..."},
        "num_pages": 1,
    }


# --- Test Cases ---

TEST_HEX_ID = "a835af"


async def test_fetch_opensky_cache_hit(
    mock_redis_client: AsyncMock, sample_enriched_data: EnrichedData
) -> None:
    """Test that cached data is returned and API is not called."""
    # Arrange: Mock Redis get_model to return cached data
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    # Return the Pydantic model instance directly
    mock_redis_client.get_model.return_value = sample_enriched_data

    # Act
    with patch("httpx.AsyncClient") as mock_async_client:
        result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    # Check that get_model was called with the key and the correct model type
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client.assert_not_called()  # API should not be called
    mock_redis_client.set_json.assert_not_awaited()  # Cache should not be set
    assert result == sample_enriched_data


@patch("httpx.AsyncClient")
async def test_fetch_opensky_cache_miss_success(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
    sample_opensky_response_vector: list,
    sample_enriched_data: EnrichedData,  # Use this for expected comparison
) -> None:
    """Test cache miss, successful API fetch, caching, and return."""
    # Arrange: Mock Redis get_model to return None (cache miss - default fixture)
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    api_url = enrichment_module.OPENSKY_API_URL

    # Mock the httpx response
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "time": 1678886401,
        "states": [sample_opensky_response_vector],
    }
    # Configure the AsyncClient instance's get method
    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    # Configure the context manager `__aenter__` to return the instance
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    # 1. Cache check
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)

    # 2. API Call
    mock_async_client_instance.get.assert_awaited_once_with(api_url, params={"icao24": TEST_HEX_ID})
    # mock_response.raise_for_status was implicitly called by the success path

    # 3. Caching result
    expected_cache_data = EnrichedData(
        callsign="SWA123",  # Cleaned callsign
        origin_country=sample_opensky_response_vector[2],
        category=sample_opensky_response_vector[17],
    )
    mock_redis_client.set_json.assert_awaited_once_with(
        cache_key, expected_cache_data, expire_seconds=enrichment_module.CACHE_TTL_SECONDS
    )

    # 4. Return value
    assert result == expected_cache_data


@patch("httpx.AsyncClient")
async def test_fetch_opensky_api_error(
    mock_async_client_cls: MagicMock, mock_redis_client: AsyncMock
) -> None:
    """Test handling of HTTP status errors from the API."""
    # Arrange: Mock Redis get_model to raise an exception
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    api_url = enrichment_module.OPENSKY_API_URL

    # Mock the httpx response to raise an error
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401  # Unauthorized
    mock_response.text = "Invalid credentials"
    http_error = httpx.HTTPStatusError(
        message="Client error '401 Unauthorized' for url ...",
        request=MagicMock(),
        response=mock_response,
    )
    mock_response.raise_for_status = MagicMock(side_effect=http_error)

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client_instance.get.assert_awaited_once_with(api_url, params={"icao24": TEST_HEX_ID})
    mock_redis_client.set_json.assert_not_awaited()  # Should not cache on error
    assert result is None


@patch("httpx.AsyncClient")
async def test_fetch_opensky_connection_error(
    mock_async_client_cls: MagicMock, mock_redis_client: AsyncMock
) -> None:
    """Test handling of connection errors during API call."""
    # Arrange: Mock Redis get_model to raise an exception
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    api_url = enrichment_module.OPENSKY_API_URL

    # Mock the client's get method to raise RequestError
    request_error = httpx.RequestError("Connection refused")
    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(side_effect=request_error)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client_instance.get.assert_awaited_once_with(api_url, params={"icao24": TEST_HEX_ID})
    mock_redis_client.set_json.assert_not_awaited()
    assert result is None


@patch("httpx.AsyncClient")
async def test_fetch_opensky_empty_response(
    mock_async_client_cls: MagicMock, mock_redis_client: AsyncMock
) -> None:
    """Test handling of empty or invalid state data from API."""
    # Arrange: Mock Redis get_model to raise an exception
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    api_url = enrichment_module.OPENSKY_API_URL

    # Mock the httpx response with empty states
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"time": 1678886401, "states": []}  # Empty states

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client_instance.get.assert_awaited_once_with(api_url, params={"icao24": TEST_HEX_ID})
    mock_redis_client.set_json.assert_not_awaited()  # Should not cache empty/invalid data
    assert result is None


@patch("httpx.AsyncClient")
async def test_fetch_opensky_redis_get_error(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
    sample_opensky_response_vector: list,
    sample_enriched_data: EnrichedData,
) -> None:
    """Test that API fetch proceeds even if Redis get fails."""
    # Arrange: Mock Redis get_model to raise an exception
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    mock_redis_client.get_model.side_effect = redis.RedisError("Simulated Redis GET Error")

    # Mock successful API response (similar to cache_miss_success test)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "time": 1678886401,
        "states": [sample_opensky_response_vector],
    }
    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client_instance.get.assert_awaited_once()
    mock_redis_client.set_json.assert_awaited_once()  # Caching is attempted
    expected_result = EnrichedData(callsign="SWA123", origin_country="United States", category=3)
    assert result == expected_result


@patch("httpx.AsyncClient")
async def test_fetch_opensky_redis_set_error(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
    sample_opensky_response_vector: list,
    sample_enriched_data: EnrichedData,
) -> None:
    """Test that result is returned even if Redis set fails."""
    # Arrange: Mock Redis get_model to raise an exception
    cache_key = f"enrich_cache:{TEST_HEX_ID}"
    mock_redis_client.get_model.return_value = None

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "time": 1678886401,
        "states": [sample_opensky_response_vector],
    }
    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Mock Redis set_json to raise an exception
    mock_redis_client.set_json.side_effect = redis.RedisError("Simulated Redis SET Error")

    # Act
    result = await fetch_opensky_data(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, EnrichedData)
    mock_async_client_instance.get.assert_awaited_once()
    mock_redis_client.set_json.assert_awaited_once()  # Caching was attempted
    expected_result = EnrichedData(callsign="SWA123", origin_country="United States", category=3)
    assert result == expected_result


# --- Test Cases: AeroAPI ---


# Remove decorators, use context managers inside
# @patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-key") # Removed decorator
async def test_fetch_aeroapi_route_cache_hit(
    mock_redis_client: AsyncMock,
    sample_route_data: RouteData,  # Removed _mock_api_key arg
) -> None:
    """Test cache hit for AeroAPI route data."""
    # Correct the cache key prefix to match the implementation
    cache_key = f"aeroapi_route:{TEST_HEX_ID}"
    mock_redis_client.get_model.return_value = sample_route_data

    # Act
    # Use patch context managers
    with (
        patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-key"),
        patch("httpx.AsyncClient") as mock_async_client,
    ):
        result = await fetch_aeroapi_route(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, RouteData)
    mock_async_client.assert_not_called()
    mock_redis_client.set_json.assert_not_awaited()
    assert result == sample_route_data


# Remove decorators, use context managers inside
# @patch("httpx.AsyncClient") # Removed decorator
# @patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key") # Removed decorator
async def test_fetch_aeroapi_route_cache_miss_success(
    # Removed _mock_api_key and mock_async_client_cls args
    mock_redis_client: AsyncMock,
    sample_aeroapi_flights_response: Dict[str, Any],
    sample_route_data: RouteData,
) -> None:
    """Test AeroAPI cache miss, successful fetch, caching, and return."""
    # Arrange
    cache_key = f"aeroapi_route:{TEST_HEX_ID}"
    api_url = f"{enrichment_module.AEROAPI_BASE_URL}/flights/{TEST_HEX_ID}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = sample_aeroapi_flights_response

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)

    # Act
    # Use patch context managers
    with (
        patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key"),
        patch("httpx.AsyncClient") as mock_async_client_cls,
    ):
        # Configure the mock inside the context
        mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance
        result = await fetch_aeroapi_route(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, RouteData)
    mock_async_client_instance.get.assert_awaited_once_with(
        api_url, headers={"x-apikey": "test-api-key"}
    )
    mock_redis_client.set_json.assert_awaited_once_with(
        cache_key,
        sample_route_data,
        expire_seconds=enrichment_module.AEROAPI_CACHE_TTL_SECONDS,
    )
    assert result == sample_route_data


# Remove decorators, use context managers inside
# @patch("httpx.AsyncClient") # Removed decorator
# @patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key") # Removed decorator
async def test_fetch_aeroapi_route_not_found(
    # Removed _mock_api_key and mock_async_client_cls args
    mock_redis_client: AsyncMock,
) -> None:
    """Test AeroAPI 404 Not Found response."""
    # Arrange
    cache_key = f"aeroapi_route:{TEST_HEX_ID}"
    api_url = f"{enrichment_module.AEROAPI_BASE_URL}/flights/{TEST_HEX_ID}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)

    # Act
    # Use patch context managers
    with (
        patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key"),
        patch("httpx.AsyncClient") as mock_async_client_cls,
    ):
        mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance
        result = await fetch_aeroapi_route(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, RouteData)
    mock_async_client_instance.get.assert_awaited_once_with(
        api_url, headers={"x-apikey": "test-api-key"}
    )
    if hasattr(mock_response, "raise_for_status") and isinstance(
        mock_response.raise_for_status, MagicMock
    ):
        mock_response.raise_for_status.assert_not_called()
    mock_redis_client.set_json.assert_not_awaited()
    assert result is None


# Remove decorators, use context managers inside
# @patch("httpx.AsyncClient") # Removed decorator
# @patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key") # Removed decorator
async def test_fetch_aeroapi_route_api_error(
    # Removed _mock_api_key and mock_async_client_cls args
    mock_redis_client: AsyncMock,
) -> None:
    """Test handling of non-404 HTTP errors from AeroAPI."""
    # Arrange
    cache_key = f"aeroapi_route:{TEST_HEX_ID}"
    api_url = f"{enrichment_module.AEROAPI_BASE_URL}/flights/{TEST_HEX_ID}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.text = "Invalid API Key"
    http_error = httpx.HTTPStatusError(
        message="Client error '401 Unauthorized' for url ...",
        request=MagicMock(),
        response=mock_response,
    )
    mock_response.raise_for_status = MagicMock(side_effect=http_error)

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)

    # Act
    # Use patch context managers
    with (
        patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", "test-api-key"),
        patch("httpx.AsyncClient") as mock_async_client_cls,
    ):
        mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance
        result = await fetch_aeroapi_route(TEST_HEX_ID, mock_redis_client)

    # Assert
    mock_redis_client.get_model.assert_awaited_once_with(cache_key, RouteData)
    mock_async_client_instance.get.assert_awaited_once_with(
        api_url, headers={"x-apikey": "test-api-key"}
    )
    mock_response.raise_for_status.assert_called_once()
    mock_redis_client.set_json.assert_not_awaited()
    assert result is None


# Remove decorator, use context manager inside
# @patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", None) # Removed decorator
async def test_fetch_aeroapi_no_api_key(
    # Removed _mock_api_key arg
    mock_redis_client: AsyncMock,
) -> None:
    """Test that function returns None if API key is not set."""
    # Arrange: Use context manager to set key to None

    # Act
    with (
        patch("backend.ingest.enrichment.FLIGHTAWARE_API_KEY", None),
        patch("httpx.AsyncClient") as mock_async_client,
    ):
        result = await fetch_aeroapi_route(TEST_HEX_ID, mock_redis_client)

    # Assert
    assert result is None
    mock_redis_client.get_model.assert_not_awaited()
    mock_async_client.assert_not_called()


# Note: Tests for Redis errors could be added similar to the OpenSky ones if desired.

# Tests will be added here

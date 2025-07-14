"""Tests for the ICAO hex code to aircraft registration conversion module."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.ingest.hex_to_registration import (
    fetch_hexdb_registration,
    hex_to_registration,
    us_hex_to_registration,
    validate_registration,
)
from backend.utils.redis_async import RedisClient

# Mark all tests in this module as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Provides a mock RedisClient with async methods."""
    mock = AsyncMock(spec=RedisClient)
    mock.get_string = AsyncMock(return_value=None)  # Default cache miss
    mock.set_string = AsyncMock()
    return mock


# --- US Hex to Registration Tests ---


def test_us_hex_to_registration_simple_numeric():
    """Test conversion of simple numeric N-numbers."""
    # N1
    assert us_hex_to_registration("A00001") == "N1"
    # N12345
    assert us_hex_to_registration("A03039") == "N12345"
    # N99999
    assert us_hex_to_registration("A1869F") == "N99999"


def test_us_hex_to_registration_alphanumeric():
    """Test conversion with alphanumeric suffixes."""
    # Test single letter suffix
    assert us_hex_to_registration("A186A0") is not None
    result = us_hex_to_registration("A186A0")
    assert result and result.startswith("N")
    assert len(result) >= 2

    # Test two letter suffix - should have digit prefix
    result = us_hex_to_registration("A30000")
    assert result and result.startswith("N")
    assert len(result) >= 3


def test_us_hex_to_registration_non_us():
    """Test that non-US hex codes return None."""
    assert us_hex_to_registration("400000") is None  # UK
    assert us_hex_to_registration("780000") is None  # China
    assert us_hex_to_registration("C00000") is None  # Canada


def test_us_hex_to_registration_out_of_range():
    """Test hex codes outside valid US range."""
    assert us_hex_to_registration("A00000") is None  # Below range
    assert us_hex_to_registration("ADF7C8") is None  # Above range
    assert us_hex_to_registration("B00000") is None  # Way above range


def test_us_hex_to_registration_lowercase():
    """Test that lowercase hex codes are handled."""
    assert us_hex_to_registration("a00001") == "N1"
    assert us_hex_to_registration("a03039") == "N12345"


def test_us_hex_to_registration_invalid():
    """Test invalid hex code handling."""
    assert us_hex_to_registration("") is None
    assert us_hex_to_registration("GGGGGG") is None
    assert us_hex_to_registration("A0") is None  # Too short


# --- hexdb.io API Tests ---


async def test_fetch_hexdb_registration_cache_hit(mock_redis_client: AsyncMock):
    """Test cache hit for hexdb registration lookup."""
    # Arrange
    hex_code = "4840D6"  # UK aircraft
    cache_key = "hex_to_reg:hexdb:4840D6"
    mock_redis_client.get_string.return_value = "G-ABCD"

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    mock_redis_client.get_string.assert_awaited_once_with(cache_key)
    mock_redis_client.set_string.assert_not_awaited()
    assert result == "G-ABCD"


@patch("httpx.AsyncClient")
async def test_fetch_hexdb_registration_cache_miss_success(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
):
    """Test successful hexdb API lookup on cache miss."""
    # Arrange
    hex_code = "4840D6"
    cache_key = "hex_to_reg:hexdb:4840D6"
    api_url = f"https://hexdb.io/api/v1/aircraft/{hex_code}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "AircraftID": 123456,
        "ModeS": "4840D6",
        "Registration": "G-ABCD",
        "ICAOTypeCode": "B738",
        "Type": "Boeing 737-800",
        "RegisteredOwners": "British Airways",
    }

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    mock_redis_client.get_string.assert_awaited_once_with(cache_key)
    mock_async_client_instance.get.assert_awaited_once_with(api_url)
    mock_redis_client.set_string.assert_awaited_once_with(
        cache_key, "G-ABCD", expire_seconds=7 * 24 * 3600
    )
    assert result == "G-ABCD"


@patch("httpx.AsyncClient")
async def test_fetch_hexdb_registration_not_found(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
):
    """Test hexdb API 404 response."""
    # Arrange
    hex_code = "FFFFFF"
    cache_key = "hex_to_reg:hexdb:FFFFFF"
    api_url = f"https://hexdb.io/api/v1/aircraft/{hex_code}"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    mock_redis_client.get_string.assert_awaited_once_with(cache_key)
    mock_async_client_instance.get.assert_awaited_once_with(api_url)
    mock_redis_client.set_string.assert_not_awaited()
    assert result is None


@patch("httpx.AsyncClient")
async def test_fetch_hexdb_registration_no_registration_in_response(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
):
    """Test hexdb API response without registration field."""
    # Arrange
    hex_code = "4840D6"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "AircraftID": 123456,
        "ModeS": "4840D6",
        # Missing Registration field
        "ICAOTypeCode": "B738",
    }

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    assert result is None
    mock_redis_client.set_string.assert_not_awaited()


@patch("httpx.AsyncClient")
async def test_fetch_hexdb_registration_api_error(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
):
    """Test hexdb API HTTP error handling."""
    # Arrange
    hex_code = "4840D6"

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    http_error = httpx.HTTPStatusError(
        message="Server error '500 Internal Server Error'",
        request=MagicMock(),
        response=mock_response,
    )
    mock_response.raise_for_status = MagicMock(side_effect=http_error)

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(return_value=mock_response)
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    assert result is None
    mock_redis_client.set_string.assert_not_awaited()


@patch("httpx.AsyncClient")
async def test_fetch_hexdb_registration_connection_error(
    mock_async_client_cls: MagicMock,
    mock_redis_client: AsyncMock,
):
    """Test hexdb API connection error handling."""
    # Arrange
    hex_code = "4840D6"

    mock_async_client_instance = AsyncMock()
    mock_async_client_instance.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))
    mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

    # Act
    result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    assert result is None
    mock_redis_client.set_string.assert_not_awaited()


async def test_fetch_hexdb_registration_without_redis():
    """Test hexdb lookup without Redis client."""
    # Act
    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"Registration": "N12345"}

        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

        result = await fetch_hexdb_registration("A03039", None)

    # Assert
    assert result == "N12345"


async def test_fetch_hexdb_registration_redis_error(mock_redis_client: AsyncMock):
    """Test hexdb lookup continues despite Redis errors."""
    # Arrange
    hex_code = "4840D6"
    mock_redis_client.get_string.side_effect = Exception("Redis connection error")
    mock_redis_client.set_string.side_effect = Exception("Redis connection error")

    # Act
    with patch("httpx.AsyncClient") as mock_async_client_cls:
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"Registration": "G-ABCD"}

        mock_async_client_instance = AsyncMock()
        mock_async_client_instance.get = AsyncMock(return_value=mock_response)
        mock_async_client_cls.return_value.__aenter__.return_value = mock_async_client_instance

        result = await fetch_hexdb_registration(hex_code, mock_redis_client)

    # Assert
    assert result == "G-ABCD"


# --- Main hex_to_registration Tests ---


async def test_hex_to_registration_us_aircraft(mock_redis_client: AsyncMock):
    """Test main function with US aircraft (algorithmic conversion)."""
    # Act
    result = await hex_to_registration("A03039", mock_redis_client)

    # Assert
    assert result == "N12345"
    # Should not call hexdb for US aircraft
    mock_redis_client.get_string.assert_not_awaited()


async def test_hex_to_registration_non_us_aircraft(mock_redis_client: AsyncMock):
    """Test main function with non-US aircraft (hexdb lookup)."""
    # Arrange
    hex_code = "4840D6"  # UK aircraft

    # Act
    with patch(
        "backend.ingest.hex_to_registration.fetch_hexdb_registration",
        AsyncMock(return_value="G-ABCD"),
    ) as mock_fetch:
        result = await hex_to_registration(hex_code, mock_redis_client)

    # Assert
    assert result == "G-ABCD"
    mock_fetch.assert_awaited_once_with(hex_code, mock_redis_client)


async def test_hex_to_registration_invalid_format():
    """Test main function with invalid hex format."""
    # Test various invalid formats
    assert await hex_to_registration("", None) is None
    assert await hex_to_registration("GGGGGG", None) is None
    assert await hex_to_registration("A0", None) is None  # Too short
    assert await hex_to_registration("A0303912", None) is None  # Too long
    assert await hex_to_registration("!@#$%^", None) is None  # Invalid chars


async def test_hex_to_registration_us_fallback_to_hexdb(mock_redis_client: AsyncMock):
    """Test US aircraft that fails algorithmic conversion falls back to hexdb."""
    # Arrange
    hex_code = "A00000"  # Invalid US range

    # Act
    with patch(
        "backend.ingest.hex_to_registration.fetch_hexdb_registration", AsyncMock(return_value=None)
    ) as mock_fetch:
        result = await hex_to_registration(hex_code, mock_redis_client)

    # Assert
    assert result is None
    mock_fetch.assert_awaited_once_with(hex_code, mock_redis_client)


async def test_hex_to_registration_lowercase_handling():
    """Test that lowercase hex codes are converted to uppercase."""
    # Act
    result = await hex_to_registration("a03039", None)

    # Assert
    assert result == "N12345"


# --- Registration Validation Tests ---


def test_validate_registration_us_nnumbers():
    """Test validation of US N-numbers."""
    # Valid US registrations
    assert validate_registration("N1") is True
    assert validate_registration("N12") is True
    assert validate_registration("N123") is True
    assert validate_registration("N1234") is True
    assert validate_registration("N12345") is True
    assert validate_registration("N123AB") is True
    assert validate_registration("N1A") is True
    assert validate_registration("N1AB") is True

    # Invalid US registrations
    assert validate_registration("N") is False
    assert validate_registration("N123456") is False  # Too many digits
    assert validate_registration("N12345ABC") is False  # Too many letters after 5 digits


def test_validate_registration_international():
    """Test validation of international registrations."""
    # UK format (G-ABCD)
    assert validate_registration("G-ABCD") is True
    assert validate_registration("G-AAAA") is True

    # Belgian format (OO-ABC)
    assert validate_registration("OO-ABC") is True
    assert validate_registration("OO-XYZ") is True

    # German format (D-ABCD)
    assert validate_registration("D-ABCD") is True

    # French format (F-ABCD)
    assert validate_registration("F-WXYZ") is True

    # Various other formats
    assert validate_registration("VH-ABC") is True  # Australia
    assert validate_registration("JA8089") is True  # Japan
    assert validate_registration("B1234") is True  # China


def test_validate_registration_invalid():
    """Test validation rejects invalid registrations."""
    assert validate_registration("") is False
    assert validate_registration("A") is False  # Too short
    assert validate_registration("123456") is False  # Numbers only
    assert validate_registration("ABCDEF") is False  # No valid pattern
    assert validate_registration("-ABCD") is False  # Invalid start
    assert validate_registration("G-") is False  # Incomplete
    assert validate_registration(None) is False  # None type


def test_validate_registration_case_insensitive():
    """Test validation is case insensitive."""
    assert validate_registration("n12345") is True
    assert validate_registration("g-abcd") is True
    assert validate_registration("oo-abc") is True

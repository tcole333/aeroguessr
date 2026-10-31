"""Tests for plane filtering service."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.schemas.game import RoundData
from backend.schemas.plane import PlaneState
from backend.services.plane_filter import PlaneFilter


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    mock_client = MagicMock()
    mock_client.get_connection = AsyncMock()
    mock_client.get_model = AsyncMock()
    mock_client.delete = AsyncMock()
    return mock_client


@pytest.fixture
def plane_filter(mock_redis):
    """Create PlaneFilter instance for testing."""
    return PlaneFilter(mock_redis)


def create_test_plane(
    hex_id: str,
    lat: float = 42.3656,
    lon: float = -71.0096,
    alt: float = 5000,
    last_update_ts: float = None,
    first_seen_ts: float = None,
    update_count: int = 5,
) -> PlaneState:
    """Create a test plane state."""
    current_time = time.time()
    return PlaneState(
        hex_ident=hex_id,
        lat=lat,
        lon=lon,
        alt=alt,
        lat_v=0.0,
        lon_v=0.0,
        alt_v=0.0,
        last_update_ts=last_update_ts or current_time,
        first_seen_ts=first_seen_ts or (current_time - 60),
        update_count=update_count,
    )


class TestPlaneFilter:
    """Test cases for PlaneFilter."""

    def test_is_plane_in_range_within_range(self, plane_filter):
        """Test plane within range detection."""
        # Boston Logan coordinates (should be in range)
        plane = create_test_plane("abc123", lat=42.3656, lon=-71.0096)
        assert plane_filter.is_plane_in_range(plane) is True

    def test_is_plane_in_range_out_of_range(self, plane_filter):
        """Test plane out of range detection."""
        # London coordinates (should be out of range)
        plane = create_test_plane("abc123", lat=51.5074, lon=-0.1278)
        assert plane_filter.is_plane_in_range(plane) is False

    def test_is_plane_recently_updated_recent(self, plane_filter):
        """Test recently updated plane detection."""
        current_time = time.time()
        plane = create_test_plane("abc123", last_update_ts=current_time - 30)
        assert plane_filter.is_plane_recently_updated(plane) is True

    def test_is_plane_recently_updated_stale(self, plane_filter):
        """Test stale plane detection."""
        current_time = time.time()
        plane = create_test_plane("abc123", last_update_ts=current_time - 120)
        assert plane_filter.is_plane_recently_updated(plane) is False

    def test_has_good_signal_quality_new_plane(self, plane_filter):
        """Test signal quality for new plane (should pass)."""
        plane = create_test_plane("abc123", update_count=2)
        assert plane_filter.has_good_signal_quality(plane) is True

    def test_has_good_signal_quality_good_frequency(self, plane_filter):
        """Test signal quality for plane with good update frequency."""
        current_time = time.time()
        plane = create_test_plane(
            "abc123",
            first_seen_ts=current_time - 60,
            update_count=10,  # 10 updates in 60 seconds = 0.167 Hz (good)
        )
        assert plane_filter.has_good_signal_quality(plane) is True

    def test_has_good_signal_quality_poor_frequency(self, plane_filter):
        """Test signal quality for plane with poor update frequency."""
        current_time = time.time()
        plane = create_test_plane(
            "abc123",
            first_seen_ts=current_time - 300,
            update_count=5,  # 5 updates in 300 seconds = 0.017 Hz (poor)
        )
        assert plane_filter.has_good_signal_quality(plane) is False

    @pytest.mark.asyncio
    async def test_get_protected_planes_no_active_rounds(self, plane_filter, mock_redis):
        """Test getting protected planes when no active rounds."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn

        protected = await plane_filter.get_protected_planes()
        assert protected == set()

    @pytest.mark.asyncio
    async def test_get_protected_planes_with_active_round(self, plane_filter, mock_redis):
        """Test getting protected planes with active round."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [b"room:TEST:meta"])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn

        # Mock get_model to return a RoundData with selected_plane_hex
        mock_round_data = RoundData(selected_plane_hex="abc123")
        mock_redis.get_model.return_value = mock_round_data

        protected = await plane_filter.get_protected_planes()
        assert protected == {"abc123"}
        mock_redis.get_model.assert_called_once_with("room:TEST:round", RoundData)

    @pytest.mark.asyncio
    async def test_filter_stale_planes_removes_out_of_range(self, plane_filter, mock_redis):
        """Test filtering removes planes that are out of range."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_redis.get_model.return_value = None  # No active rounds

        planes = {
            "abc123": create_test_plane("abc123", lat=42.3656, lon=-71.0096),  # In range
            "def456": create_test_plane("def456", lat=51.5074, lon=-0.1278),  # Out of range
        }

        stale = await plane_filter.filter_stale_planes(planes)
        assert "def456" in stale
        assert "abc123" not in stale

    @pytest.mark.asyncio
    async def test_filter_stale_planes_removes_stale_updates(self, plane_filter, mock_redis):
        """Test filtering removes planes with stale updates."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_redis.get_model.return_value = None  # No active rounds

        current_time = time.time()
        planes = {
            "abc123": create_test_plane("abc123", last_update_ts=current_time - 30),  # Recent
            "def456": create_test_plane("def456", last_update_ts=current_time - 120),  # Stale
        }

        stale = await plane_filter.filter_stale_planes(planes)
        assert "def456" in stale
        assert "abc123" not in stale

    @pytest.mark.asyncio
    async def test_filter_stale_planes_removes_poor_signal_quality(self, plane_filter, mock_redis):
        """Test filtering removes planes with poor signal quality."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn
        mock_redis.get_model.return_value = None  # No active rounds

        current_time = time.time()
        planes = {
            "abc123": create_test_plane(
                "abc123",
                first_seen_ts=current_time - 60,
                update_count=10,  # Good quality
            ),
            "def456": create_test_plane(
                "def456",
                first_seen_ts=current_time - 300,
                update_count=5,  # Poor quality
            ),
        }

        stale = await plane_filter.filter_stale_planes(planes)
        assert "def456" in stale
        assert "abc123" not in stale

    @pytest.mark.asyncio
    async def test_filter_stale_planes_protects_active_round_planes(self, plane_filter, mock_redis):
        """Test filtering protects planes in active rounds."""
        mock_conn = AsyncMock()
        mock_conn.scan.return_value = (0, [b"room:TEST:meta"])
        mock_redis.get_connection.return_value.__aenter__.return_value = mock_conn

        # Mock get_model to return a RoundData with selected_plane_hex
        mock_round_data = RoundData(selected_plane_hex="def456")
        mock_redis.get_model.return_value = mock_round_data

        planes = {
            "abc123": create_test_plane("abc123", lat=51.5074, lon=-0.1278),  # Out of range
            "def456": create_test_plane(
                "def456", lat=51.5074, lon=-0.1278
            ),  # Out of range but protected
        }

        stale = await plane_filter.filter_stale_planes(planes)
        assert "abc123" in stale
        assert "def456" not in stale  # Protected

    @pytest.mark.asyncio
    async def test_remove_planes_from_redis(self, plane_filter, mock_redis):
        """Test removing planes from Redis."""
        mock_redis.delete = AsyncMock()

        await plane_filter.remove_planes_from_redis(["abc123", "def456"])

        # Verify Redis delete calls through wrapper
        assert mock_redis.delete.call_count == 2
        mock_redis.delete.assert_any_call("plane:abc123")
        mock_redis.delete.assert_any_call("plane:def456")

    @pytest.mark.asyncio
    async def test_remove_planes_from_redis_empty_list(self, plane_filter, mock_redis):
        """Test removing empty list of planes does nothing."""
        mock_redis.delete = AsyncMock()

        await plane_filter.remove_planes_from_redis([])

        # Verify no Redis calls
        mock_redis.delete.assert_not_called()

"""Tests for the PositionSmootherENU (ENU coordinate frame Kalman filter)."""

import math

import pytest

from backend.ingest.smoother_enu import PositionSmootherENU


@pytest.fixture
def origin_ll() -> tuple[float, float]:
    """Reference origin at Boston Logan Airport."""
    return (42.3656, -71.0096)


@pytest.fixture
def initial_pos() -> tuple[float, float, float]:
    """Initial position (lat, lon, alt) near Boston."""
    return (42.3656, -71.0096, 10000.0)  # lat, lon, alt in feet


@pytest.fixture
def smoother(
    initial_pos: tuple[float, float, float], origin_ll: tuple[float, float]
) -> PositionSmootherENU:
    """Create a smoother with default noise parameters."""
    return PositionSmootherENU(
        initial_pos_deg_ft=initial_pos,
        origin_ll=origin_ll,
    )


class TestInitialization:
    """Test smoother initialization."""

    def test_initial_position(
        self, smoother: PositionSmootherENU, initial_pos: tuple[float, float, float]
    ) -> None:
        """Test that initial position is set correctly."""
        pos = smoother.position
        assert pos[0] == pytest.approx(initial_pos[0], rel=1e-6)
        assert pos[1] == pytest.approx(initial_pos[1], rel=1e-6)
        assert pos[2] == pytest.approx(initial_pos[2], rel=1e-6)

    def test_initial_velocity_is_zero(self, smoother: PositionSmootherENU) -> None:
        """Test that initial velocity is zero."""
        vel = smoother.velocity
        assert vel[0] == pytest.approx(0.0, abs=1e-10)
        assert vel[1] == pytest.approx(0.0, abs=1e-10)
        assert vel[2] == pytest.approx(0.0, abs=1e-10)


class TestVelocityDirection:
    """Test that velocity components are correctly mapped from ENU to lat/lon.

    This is critical for correct heading calculation:
    - lat_v (North velocity) should come from vy (North in ENU)
    - lon_v (East velocity) should come from vx (East in ENU)
    """

    def test_northbound_velocity(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying north should have positive lat_v, zero lon_v."""
        # Start at origin
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move the plane north (increase latitude)
        dt = 1.0
        north_offset = 0.01  # degrees north
        new_pos = (initial[0] + north_offset, initial[1], initial[2])

        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity

        # lat_v should be positive (moving north)
        assert lat_v > 0, f"Expected positive lat_v for northbound, got {lat_v}"
        # lon_v should be near zero (not moving east/west)
        assert abs(lon_v) < abs(lat_v) * 0.1, f"Expected lon_v near zero, got {lon_v}"

    def test_eastbound_velocity(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying east should have positive lon_v, zero lat_v."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move the plane east (increase longitude)
        dt = 1.0
        east_offset = 0.01  # degrees east
        new_pos = (initial[0], initial[1] + east_offset, initial[2])

        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity

        # lon_v should be positive (moving east)
        assert lon_v > 0, f"Expected positive lon_v for eastbound, got {lon_v}"
        # lat_v should be near zero (not moving north/south)
        assert abs(lat_v) < abs(lon_v) * 0.1, f"Expected lat_v near zero, got {lat_v}"

    def test_southbound_velocity(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying south should have negative lat_v, zero lon_v."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move the plane south (decrease latitude)
        dt = 1.0
        south_offset = -0.01  # degrees south
        new_pos = (initial[0] + south_offset, initial[1], initial[2])

        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity

        # lat_v should be negative (moving south)
        assert lat_v < 0, f"Expected negative lat_v for southbound, got {lat_v}"
        # lon_v should be near zero
        assert abs(lon_v) < abs(lat_v) * 0.1, f"Expected lon_v near zero, got {lon_v}"

    def test_westbound_velocity(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying west should have negative lon_v, zero lat_v."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move the plane west (decrease longitude)
        dt = 1.0
        west_offset = -0.01  # degrees west
        new_pos = (initial[0], initial[1] + west_offset, initial[2])

        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity

        # lon_v should be negative (moving west)
        assert lon_v < 0, f"Expected negative lon_v for westbound, got {lon_v}"
        # lat_v should be near zero
        assert abs(lat_v) < abs(lon_v) * 0.1, f"Expected lat_v near zero, got {lat_v}"


class TestHeadingCalculation:
    """Test that heading can be correctly calculated from velocity.

    Heading convention: 0 = North, 90 = East, 180 = South, 270 = West
    Formula: heading = atan2(lon_v, lat_v) in degrees
    """

    def calculate_heading(self, lat_v: float, lon_v: float) -> float:
        """Calculate heading from velocity components (same as frontend)."""
        bearing = math.atan2(lon_v, lat_v) * (180 / math.pi)
        return (bearing + 360) % 360

    def test_heading_north(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying north should have heading ~0 degrees."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move north
        dt = 1.0
        new_pos = (initial[0] + 0.01, initial[1], initial[2])
        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity
        heading = self.calculate_heading(lat_v, lon_v)

        # Heading should be close to 0 (North)
        assert heading < 15 or heading > 345, f"Expected heading ~0 for northbound, got {heading}"

    def test_heading_east(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying east should have heading ~90 degrees."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move east
        dt = 1.0
        new_pos = (initial[0], initial[1] + 0.01, initial[2])
        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity
        heading = self.calculate_heading(lat_v, lon_v)

        # Heading should be close to 90 (East)
        assert 75 < heading < 105, f"Expected heading ~90 for eastbound, got {heading}"

    def test_heading_south(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying south should have heading ~180 degrees."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move south
        dt = 1.0
        new_pos = (initial[0] - 0.01, initial[1], initial[2])
        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity
        heading = self.calculate_heading(lat_v, lon_v)

        # Heading should be close to 180 (South)
        assert 165 < heading < 195, f"Expected heading ~180 for southbound, got {heading}"

    def test_heading_west(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying west should have heading ~270 degrees."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move west
        dt = 1.0
        new_pos = (initial[0], initial[1] - 0.01, initial[2])
        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity
        heading = self.calculate_heading(lat_v, lon_v)

        # Heading should be close to 270 (West)
        assert 255 < heading < 285, f"Expected heading ~270 for westbound, got {heading}"

    def test_heading_northeast(self, origin_ll: tuple[float, float]) -> None:
        """Plane flying northeast should have heading ~45 degrees."""
        initial = (origin_ll[0], origin_ll[1], 10000.0)
        smoother = PositionSmootherENU(initial, origin_ll)

        # Move northeast (equal north and east)
        dt = 1.0
        offset = 0.01
        new_pos = (initial[0] + offset, initial[1] + offset, initial[2])
        smoother.predict(dt)
        smoother.update(new_pos)

        lat_v, lon_v, _ = smoother.velocity
        heading = self.calculate_heading(lat_v, lon_v)

        # Heading should be close to 45 (Northeast)
        assert 30 < heading < 60, f"Expected heading ~45 for northeast, got {heading}"


class TestStateVector:
    """Test the state vector output format."""

    def test_state_returns_correct_format(
        self, smoother: PositionSmootherENU, initial_pos: tuple[float, float, float]
    ) -> None:
        """State vector should be [lat, lon, alt, lat_v, lon_v, alt_v]."""
        state = smoother.state

        assert len(state) == 6
        # Position components
        assert state[0] == pytest.approx(initial_pos[0], rel=1e-6)  # lat
        assert state[1] == pytest.approx(initial_pos[1], rel=1e-6)  # lon
        assert state[2] == pytest.approx(initial_pos[2], rel=1e-6)  # alt
        # Velocity components (should be zero initially)
        assert state[3] == pytest.approx(0.0, abs=1e-10)  # lat_v
        assert state[4] == pytest.approx(0.0, abs=1e-10)  # lon_v
        assert state[5] == pytest.approx(0.0, abs=1e-10)  # alt_v

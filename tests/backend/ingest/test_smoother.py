"""Tests for the PositionSmoother using filterpy."""

import numpy as np
import pytest

from backend.ingest.smoother import PositionSmoother


@pytest.fixture
def initial_pos() -> np.ndarray:
    return np.array([42.0, -71.0, 10000.0])  # lat, lon, alt


@pytest.fixture
def smoother(initial_pos: np.ndarray) -> PositionSmoother:
    # Noise values are somewhat arbitrary for basic testing
    process_noise = 0.5
    measurement_noise = 5.0
    return PositionSmoother(initial_pos, process_noise, measurement_noise)


def test_smoother_initialization(smoother: PositionSmoother, initial_pos: np.ndarray) -> None:
    """Test that the smoother initializes correctly."""
    assert smoother.dim_state == 6
    assert smoother.dim_measurement == 3
    assert smoother.filter is not None

    # Check initial state (position set, velocity zero)
    assert np.allclose(smoother.filter.x[:3], initial_pos)
    assert np.allclose(smoother.filter.x[3:], np.zeros(3))

    # Check dimensions of matrices
    assert smoother.filter.H.shape == (3, 6)
    assert smoother.filter.R.shape == (3, 3)
    assert smoother.filter.P.shape == (6, 6)
    assert smoother.filter.F.shape == (6, 6)  # Initial F
    assert smoother.filter.Q.shape == (6, 6)  # Initial Q (will be set in predict)


def test_smoother_predict(smoother: PositionSmoother, initial_pos: np.ndarray) -> None:
    """Test the predict step."""
    dt = 1.0  # 1 second time step
    # Capture covariance BEFORE prediction
    initial_covariance = smoother.covariance.copy()

    smoother.predict(dt)

    predicted_state = smoother.state
    # Get covariance AFTER prediction
    predicted_covariance = smoother.covariance

    # Position should not change with zero initial velocity in predict
    assert np.allclose(predicted_state[:3], initial_pos)
    # Velocity should remain zero
    assert np.allclose(predicted_state[3:], np.zeros(3))
    # Covariance (uncertainty) should generally increase during prediction
    # Check if the trace (sum of diagonal variances) increased
    assert np.trace(predicted_covariance) > np.trace(initial_covariance)
    # Or check if at least some diagonal elements increased
    # assert np.any(np.diag(predicted_covariance) > np.diag(initial_covariance))


def test_smoother_predict_with_velocity(smoother: PositionSmoother) -> None:
    """Test predict step when there is initial velocity."""
    dt = 2.0
    # Set some initial velocity [lat_v, lon_v, alt_v]
    initial_velocity = np.array([0.01, -0.02, -10.0])
    smoother.filter.x[3:] = initial_velocity
    initial_pos = smoother.position.copy()

    smoother.predict(dt)

    predicted_pos = smoother.position
    expected_pos = initial_pos + initial_velocity * dt

    # Check if position changed according to velocity * dt
    assert np.allclose(predicted_pos, expected_pos)
    # Velocity should remain constant in predict step for const vel model
    assert np.allclose(smoother.velocity, initial_velocity)


def test_smoother_update(smoother: PositionSmoother, initial_pos: np.ndarray) -> None:
    """Test the update step."""
    dt = 1.0
    smoother.predict(dt)
    initial_state_pred = smoother.state.copy()
    initial_cov_pred = smoother.covariance.copy()

    # Simulate a new measurement slightly different from the initial one
    measurement = initial_pos + np.array([0.01, -0.01, 5.0])
    smoother.update(measurement)

    updated_state = smoother.state
    updated_cov = smoother.covariance

    # State should move towards the measurement from the predicted state
    # Check if the updated position is between predicted and measurement
    # (This isn't strictly guaranteed, but likely for reasonable noise)
    pred_pos = initial_state_pred[:3]
    updated_pos = updated_state[:3]
    # Assert that the update moved the estimate closer to the measurement than prediction was
    assert np.linalg.norm(updated_pos - measurement) < np.linalg.norm(pred_pos - measurement)

    # Covariance should decrease after update
    assert np.all(np.diag(updated_cov) < np.diag(initial_cov_pred))


def test_smoother_properties(smoother: PositionSmoother, initial_pos: np.ndarray) -> None:
    """Test the state, position, velocity, and covariance properties."""
    assert np.allclose(smoother.state[:3], smoother.position)
    assert np.allclose(smoother.state[3:], smoother.velocity)
    assert np.allclose(smoother.position, initial_pos)
    assert np.allclose(smoother.velocity, np.zeros(3))
    assert smoother.covariance.shape == (6, 6)

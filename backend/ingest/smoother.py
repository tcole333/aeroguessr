"""Provides position smoothing using a Kalman filter from the filterpy library."""

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter


class PositionSmoother:
    """Wraps filterpy.kalman.KalmanFilter for aircraft position smoothing.

    Uses a 6-state constant velocity model:
    [lat, lon, alt, lat_vel, lon_vel, alt_vel]
    Measurement is [lat, lon, alt].
    """

    def __init__(
        self, initial_pos: np.ndarray, process_noise: float, measurement_noise: float
    ) -> None:
        """Initialize the Kalman filter.

        Args:
            initial_pos: Initial measurement [lat, lon, alt].
            process_noise: Variance of the process noise (acceleration uncertainty).
            measurement_noise: Variance of the measurement noise (sensor inaccuracy).
        """
        self.dim_state = 6
        self.dim_measurement = 3

        self.filter = KalmanFilter(dim_x=self.dim_state, dim_z=self.dim_measurement)

        # Initial state estimate (position based on first measurement, zero velocity)
        self.filter.x = np.zeros(self.dim_state)
        self.filter.x[: self.dim_measurement] = initial_pos

        # State transition matrix F (defined in predict)
        # Will be updated based on dt in predict

        # Measurement function H
        self.filter.H = np.zeros((self.dim_measurement, self.dim_state))
        self.filter.H[0, 0] = 1.0  # lat
        self.filter.H[1, 1] = 1.0  # lon
        self.filter.H[2, 2] = 1.0  # alt

        # Measurement noise covariance R
        self.filter.R = np.eye(self.dim_measurement) * measurement_noise

        # Process noise covariance Q (defined in predict)
        # Will be calculated using Q_discrete_white_noise based on dt
        self._process_noise_var = process_noise  # Store variance for Q calculation

        # Initial state covariance P (uncertainty)
        # High initial uncertainty, especially in velocity
        self.filter.P = np.eye(self.dim_state) * 500.0
        self.filter.P[self.dim_measurement :, self.dim_measurement :] *= 1000.0

    def predict(self, dt: float) -> None:
        """Predict the next state based on the time elapsed.

        Args:
            dt: Time step (delta time) in seconds since the last update.
        """
        # Update state transition matrix F for the given dt
        self.filter.F = np.eye(self.dim_state)
        for i in range(self.dim_measurement):
            self.filter.F[i, i + self.dim_measurement] = dt

        # Update process noise Q using filterpy helper
        # This assumes noise is applied independently to acceleration in each dimension
        # Using block_size=3 because noise affects lat, lon, alt accelerations
        # Order=2 because model is constant velocity (position is 2nd integral of acceleration)
        self.filter.Q = Q_discrete_white_noise(
            dim=2, dt=dt, var=self._process_noise_var, block_size=3, order_by_dim=False
        )
        # The Q matrix from filterpy needs rearrangement for our state [pos, vel]
        # It's generated for [pos, vel, acc]. We only need the pos/vel parts.
        # Let's reconstruct manually for clarity in the [lat, lon, alt, lat_v, lon_v, alt_v] order
        # Q = [ Q_pos   Q_pos_vel ]
        #     [ Q_vel_pos Q_vel   ]
        q_cv = Q_discrete_white_noise(dim=2, dt=dt, var=self._process_noise_var)
        self.filter.Q = np.kron(np.eye(3), q_cv)

        self.filter.predict()

    def update(self, z: np.ndarray) -> None:
        """Update the filter state with a new measurement.

        Args:
            z: Measurement vector [lat, lon, alt].
        """
        self.filter.update(z)

    @property
    def state(self) -> np.ndarray:
        """Returns the current estimated state vector x."""
        return self.filter.x

    @property
    def position(self) -> np.ndarray:
        """Returns the current estimated position [lat, lon, alt]."""
        return self.filter.x[: self.dim_measurement]

    @property
    def velocity(self) -> np.ndarray:
        """Returns the current estimated velocity [lat_v, lon_v, alt_v]."""
        return self.filter.x[self.dim_measurement :]

    @property
    def covariance(self) -> np.ndarray:
        """Returns the current state covariance matrix P."""
        return self.filter.P

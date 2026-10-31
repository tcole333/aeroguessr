"""Improved position smoother working in a local ENU (East-North-Up) metre frame.

Motivation
~~~~~~~~~~
An earlier smoother (since deleted) operated directly on latitude/longitude
values expressed in **degrees** and an altitude expressed in **feet**.
The large unit mismatch (≈100 000× between degrees and feet) causes poor
numerical conditioning and forces the Kalman filter to rely on very high
process/measurement noise values, often leading to numerical
instabilities (matrix inversion failures) observed on the Raspberry Pi.

This implementation converts every incoming measurement to a *local*
Cartesian metre frame anchored at a configurable origin – typically the
receiver antenna location – and uses SI-consistent units throughout the
filter.  The public API remains *lat/lon/alt* in the same units the rest
of the ingest pipeline expects so that downstream code changes are
minimal.

Design choices
--------------
•  **Frame:** simple equirectangular (flat-Earth) approximation is
   sufficient for the ≈300 NM (≈550 km) radius our antenna covers.  We
   avoid pulling in pyproj or similar heavy dependencies.
•  **State vector:** 6-state constant-velocity model, `[x, y, z, ẋ, ẏ, ż]`.
•  **Noise tuning:** accepts *per-axis* process and measurement noise
   (standard deviation, *not variance*) in metres and metres/second.
•  **Initial covariance P:** moderate (100 m² position, 25 ( m/s )²
   velocity) so the filter converges quickly without wild initial jumps.
•  **Unit conversions:** altitude is converted feet ⇄ metres using the
   standard factor (1 ft = 0.3048 m).
"""

from __future__ import annotations

import math
from typing import Iterable, Tuple

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter

__all__ = ["PositionSmootherENU"]

_FT_TO_M = 0.3048
_M_TO_FT = 1 / _FT_TO_M
_SECONDS_PER_MINUTE = 60


class PositionSmootherENU:
    """Constant-velocity Kalman smoother in ENU metres."""

    def __init__(
        self,
        initial_pos_deg_ft: Tuple[float, float, float],
        origin_ll: Tuple[float, float],
        process_noise_std: Tuple[float, float, float] = (2.0, 2.0, 5.0),
        measurement_noise_std: Tuple[float, float, float] = (30.0, 30.0, 60.0),
    ) -> None:
        """Create a new smoother.

        Args
        ----
        initial_pos_deg_ft: `(lat_deg, lon_deg, alt_ft)` first measurement.
        origin_ll: antenna reference `(lat0_deg, lon0_deg)`.
        process_noise_std: per-axis *acceleration* σₐ [m/s²].
        measurement_noise_std: per-axis position σᵣ [m].
        """
        self._lat0, self._lon0 = origin_ll
        # metres per degree at origin
        self._m_per_deg_lat = 111_320.0
        self._m_per_deg_lon = 111_320.0 * math.cos(math.radians(self._lat0))

        # Convert first measurement to metres
        x0, y0, z0 = self._to_m(initial_pos_deg_ft)

        self._kf = KalmanFilter(dim_x=6, dim_z=3)
        # state vector [x, y, z, vx, vy, vz] (all metres / metres per second)
        self._kf.x = np.array([x0, y0, z0, 0.0, 0.0, 0.0])

        # F will be filled in predict(dt)
        # Measurement matrix H
        self._kf.H = np.zeros((3, 6))
        self._kf.H[0, 0] = 1.0
        self._kf.H[1, 1] = 1.0
        self._kf.H[2, 2] = 1.0

        # Measurement noise R (variance)
        self._kf.R = np.diag(np.square(measurement_noise_std))

        # Store per-axis acceleration σ for Q computation
        self._process_noise_std = np.array(process_noise_std)

        # Initial covariance P
        self._kf.P = np.diag([100.0, 100.0, 300.0, 25.0, 25.0, 100.0])

    # ---------------------------------------------------------------------
    # Public helpers
    # ---------------------------------------------------------------------

    def predict(self, dt: float) -> None:
        """Time-update the filter by *dt* seconds."""
        if dt <= 0.0:
            return

        # State-transition matrix F for constant velocity
        F = np.eye(6)
        F[0, 3] = dt
        F[1, 4] = dt
        F[2, 5] = dt
        self._kf.F = F

        # Each axis's process noise is a 2x2 block over its (position, velocity). The state
        # is ordered [x, y, z, vx, vy, vz], so axis i's block sits at rows/columns (i, i + 3);
        # stacking the blocks along the diagonal would couple north velocity to climb rate.
        Q = np.zeros((6, 6))
        for axis, sigma_a in enumerate(self._process_noise_std):
            axis_indices = [axis, axis + 3]
            Q[np.ix_(axis_indices, axis_indices)] = Q_discrete_white_noise(
                dim=2, dt=dt, var=sigma_a**2
            )
        self._kf.Q = Q

        self._kf.predict()

    def update(self, measurement_deg_ft: Tuple[float, float, float]) -> None:
        """Measurement-update with *lat/lon/alt* in (deg, deg, ft)."""
        z = np.array(self._to_m(measurement_deg_ft))
        self._kf.update(z)

    # ------------------------------------------------------------------
    # Derived properties (in original units)
    # ------------------------------------------------------------------

    @property
    def position(self) -> Tuple[float, float, float]:
        """Current position as `(lat_deg, lon_deg, alt_ft)`."""
        x, y, z = self._kf.x[:3]
        return self._to_deg_ft((x, y, z))

    @property
    def velocity(self) -> Tuple[float, float, float]:
        """Current velocity as `(lat_deg/s, lon_deg/s, alt_ft/min)`.

        Note: velocities are returned in the same mixed units expected by the
        existing ingest pipeline so downstream code does not change yet.

        Internal ENU frame:
        - vx = East velocity (m/s)
        - vy = North velocity (m/s)
        - vz = Up velocity (m/s)

        Output:
        - lat_v = North velocity in degrees/s (from vy)
        - lon_v = East velocity in degrees/s (from vx)
        - alt_v = Up velocity in feet/minute (from vz), the unit ADS-B and pilots use
        """
        vx, vy, vz = self._kf.x[3:]
        # vx is East (longitude direction), vy is North (latitude direction)
        lat_v = vy / self._m_per_deg_lat  # North velocity -> lat degrees/s
        lon_v = vx / self._m_per_deg_lon  # East velocity -> lon degrees/s
        alt_v = vz * _M_TO_FT * _SECONDS_PER_MINUTE  # m/s → ft/min
        return lat_v, lon_v, alt_v

    # Preserve original ingest interface ----------------------------------
    @property
    def state(self) -> np.ndarray:
        """State vector in **mixed units** expected by ingest (deg/ft).

        Returns np.ndarray([lat_deg, lon_deg, alt_ft, lat_deg/s, lon_deg/s, alt_ft/min])
        so the rest of the ingest code can remain unchanged for now.
        """
        lat_deg, lon_deg, alt_ft = self.position
        lat_v, lon_v, alt_v = self.velocity
        return np.array([lat_deg, lon_deg, alt_ft, lat_v, lon_v, alt_v])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_m(self, pos_deg_ft: Iterable[float]) -> Tuple[float, float, float]:
        lat_deg, lon_deg, alt_ft = pos_deg_ft
        x = (lon_deg - self._lon0) * self._m_per_deg_lon
        y = (lat_deg - self._lat0) * self._m_per_deg_lat
        z = alt_ft * _FT_TO_M
        return x, y, z

    def _to_deg_ft(self, pos_m: Iterable[float]) -> Tuple[float, float, float]:
        x, y, z = pos_m
        lat_deg = y / self._m_per_deg_lat + self._lat0
        lon_deg = x / self._m_per_deg_lon + self._lon0
        alt_ft = z * _M_TO_FT
        return lat_deg, lon_deg, alt_ft

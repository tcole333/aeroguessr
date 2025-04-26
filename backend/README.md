# Backend

This directory contains the Python backend service for the Plane Guessing Game, built with FastAPI.

## Overview

The backend is responsible for:

- Ingesting and parsing live ADS-B flight data.
- Enriching flight data with details like origin, destination, and aircraft type.
- Managing game rooms and player state using Redis.
- Handling real-time communication with clients via WebSockets.
- Providing a REST API for room management and other actions.

## Key Components

### Ingest (`backend/ingest/`)

Handles the connection to the ADS-B data source (e.g., `dump1090`) and parsing the raw data streams.

**`parser.py`**:

- Contains the `parse_sbs_message` function, which takes raw SBS-1 formatted strings (typically from TCP port 30003) and attempts to parse them into a structured `RawMessage` object.
- **Input:** A single line string in SBS-1 format and a reception timestamp.
- **Output:** A `RawMessage` dataclass instance containing extracted fields (like `hex_ident`, `msg_type`, `altitude`, `latitude`, `longitude`, `callsign`, etc.) if the input is a valid `MSG` type message, otherwise `None`.
- **Usage Example:**

  ```python
  import time
  from backend.ingest.parser import parse_sbs_message

  sbs_line = "MSG,3,1,1,AC1234,1,2023/01/01,12:00:00.000,2023/01/01,12:00:00.000,,35000,,,47.123,-1.456,,,,"
  timestamp = time.time()
  raw_message = parse_sbs_message(sbs_line, timestamp)

  if raw_message:
      print(f"Parsed Plane {raw_message.hex_ident}: Alt={raw_message.altitude}, Lat={raw_message.latitude}, Lon={raw_message.longitude}")
  ```

**`smoother.py`**:

- Provides the `PositionSmoother` class, which wraps a Kalman filter (`filterpy.kalman.KalmanFilter`) to smooth noisy position data (latitude, longitude, altitude).
- Uses a constant velocity model (6 state dimensions: position + velocity for lat/lon/alt).
- Requires initial position measurement and configurable process/measurement noise parameters.
- **Input:** Initial position (`np.ndarray`), process noise variance (`float`), measurement noise variance (`float`). Subsequently takes time delta (`dt: float`) for `predict` and new position measurements (`np.ndarray`) for `update`.
- **Output:** Access smoothed state via properties like `position`, `velocity`, `state`.
- **Usage Example:**

  ```python
  import numpy as np
  from backend.ingest.smoother import PositionSmoother

  # Example initial measurement and noise
  initial_measurement = np.array([42.123, -71.456, 30000.0])
  process_noise_variance = 0.5  # How much velocity might change
  measurement_noise_variance = 10.0 # How noisy the sensor reading is

  smoother = PositionSmoother(
      initial_pos=initial_measurement,
      process_noise=process_noise_variance,
      measurement_noise=measurement_noise_variance
  )

  # Later, when a new message arrives...
  dt = 1.5 # Time since last update in seconds
  new_measurement = np.array([42.124, -71.458, 29950.0])

  smoother.predict(dt)
  smoother.update(new_measurement)

  smoothed_position = smoother.position
  smoothed_velocity = smoother.velocity
  print(f"Smoothed Pos: {smoothed_position}, Smoothed Vel: {smoothed_velocity}")
  ```

**`main.py`**:

- Contains the main asynchronous ingest loop (`run_ingest_loop`) and message handler (`handle_message`).
- Connects to the configured ADS-B TCP source (`ADSB_HOST`, `ADSB_PORT`).
- Reads incoming SBS-1 messages line by line.
- Uses `parser.parse_sbs_message` to decode valid messages.
- Manages `PositionSmoother` instances in memory for each active aircraft hex ID.
- Calculates time deltas (`dt`) between position updates for each aircraft.
- Calls `smoother.predict(dt)` and `smoother.update(measurement)`.
- Stores the resulting smoothed `PlaneState` (a Pydantic model) in Redis using `RedisClient.set_json`, applying a TTL (`PLANE_TTL_SECONDS`).
- Handles connection errors and attempts reconnections.
- Can be run directly (`python -m backend.ingest.main`) using environment variables for configuration.

_(Further sections on Services, Routes, Schemas, Testing, Running Locally will be added here)_

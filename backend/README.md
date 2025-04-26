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

_(Further sections on Services, Routes, Schemas, Testing, Running Locally will be added here)_

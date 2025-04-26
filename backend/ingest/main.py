"""Main ADS-B ingest loop.

Connects to TCP source, parses messages, smooths data, and stores in Redis.
"""

import asyncio
import logging
import os
import time
from typing import Dict

import numpy as np
from pydantic import BaseModel, Field

from backend.ingest.parser import RawMessage, parse_sbs_message
from backend.ingest.smoother import PositionSmoother
from backend.utils.redis_async import RedisClient

# --- Configuration ---
ADSB_HOST = os.getenv("ADSB_HOST", "localhost")
ADSB_PORT = int(os.getenv("ADSB_PORT", 30003))
KALMAN_PROCESS_NOISE = float(os.getenv("KALMAN_PROCESS_NOISE", 0.5))
KALMAN_MEASUREMENT_NOISE = float(os.getenv("KALMAN_MEASUREMENT_NOISE", 10.0))
PLANE_TTL_SECONDS = int(os.getenv("PLANE_TTL_SECONDS", 300))
RECONNECT_DELAY = 5  # Seconds to wait before retrying connection

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# --- Data Structures ---
class PlaneState(BaseModel):
    """Represents the smoothed state of an aircraft stored in Redis."""

    hex_ident: str = Field(..., description="Aircraft ICAO hex identifier.")
    lat: float = Field(..., description="Smoothed latitude.")
    lon: float = Field(..., description="Smoothed longitude.")
    alt: float = Field(..., description="Smoothed altitude in feet.")
    lat_v: float = Field(..., description="Smoothed latitude velocity.")
    lon_v: float = Field(..., description="Smoothed longitude velocity.")
    alt_v: float = Field(..., description="Smoothed altitude velocity (fpm).")
    last_update_ts: float = Field(..., description="Timestamp of the last update.")
    # TODO: Add other fields like callsign, ground speed, track etc. later


# Runtime state (in-memory)
active_smoothers: Dict[str, PositionSmoother] = {}
last_timestamps: Dict[str, float] = {}


# --- Main Ingest Logic ---
async def handle_message(msg: RawMessage, redis_client: RedisClient) -> None:
    """Process a parsed RawMessage: update smoother and store in Redis."""
    if not msg.latitude or not msg.longitude or not msg.altitude:
        # logger.debug(f"Skipping message for {msg.hex_ident}: Missing position data.")
        return  # Skip messages without position

    hex_ident = msg.hex_ident
    current_time = msg.timestamp
    measurement = np.array([msg.latitude, msg.longitude, msg.altitude])

    smoother = active_smoothers.get(hex_ident)

    if smoother is None:
        logger.info(f"Creating new smoother for {hex_ident}.")
        smoother = PositionSmoother(
            initial_pos=measurement,
            process_noise=KALMAN_PROCESS_NOISE,
            measurement_noise=KALMAN_MEASUREMENT_NOISE,
        )
        active_smoothers[hex_ident] = smoother
        # Don't update or predict on the very first message, just store initial state
        last_timestamps[hex_ident] = current_time
        # Initial velocity is zero
        smoothed_state = np.concatenate((measurement, np.zeros(3)))
    else:
        last_time = last_timestamps.get(hex_ident, current_time)
        dt = max(0.01, current_time - last_time)  # Ensure dt is positive

        try:
            smoother.predict(dt)
            smoother.update(measurement)
            smoothed_state = smoother.state
            last_timestamps[hex_ident] = current_time
            # logger.debug(f"Updated smoother for {hex_ident}. dt={dt:.2f}s")
        except np.linalg.LinAlgError as e:
            logger.error(f"Kalman filter error for {hex_ident}: {e}. Resetting smoother.")
            # Reset smoother on numerical instability
            del active_smoothers[hex_ident]
            del last_timestamps[hex_ident]
            return

    # Prepare data for Redis
    plane_data = PlaneState(
        hex_ident=hex_ident,
        lat=smoothed_state[0],
        lon=smoothed_state[1],
        alt=smoothed_state[2],
        lat_v=smoothed_state[3],
        lon_v=smoothed_state[4],
        alt_v=smoothed_state[5],
        last_update_ts=current_time,
    )

    # Store in Redis
    redis_key = f"plane:{hex_ident}"
    try:
        await redis_client.set_json(redis_key, plane_data, expire_seconds=PLANE_TTL_SECONDS)
        # logger.debug(f"Stored {redis_key} in Redis. TTL={PLANE_TTL_SECONDS}s")
    except Exception as e:
        logger.error(f"Failed to store {redis_key} in Redis: {e}")


async def run_ingest_loop() -> None:
    """Connect to ADS-B source and process messages indefinitely."""
    redis_client = RedisClient()
    logger.info("Ingest loop starting. Connecting to Redis...")
    # Test Redis connection early
    try:
        conn = await redis_client.get_connection()
        await conn.ping()
        logger.info("Redis connection successful.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}. Exiting.")
        return

    while True:
        try:
            logger.info(f"Connecting to ADS-B source at {ADSB_HOST}:{ADSB_PORT}...")
            reader, writer = await asyncio.open_connection(ADSB_HOST, ADSB_PORT)
            logger.info("Connected to ADS-B source.")

            while True:
                try:
                    line_bytes = await reader.readline()
                    if not line_bytes:
                        logger.warning("Connection closed by ADS-B source.")
                        break  # Break inner loop to reconnect

                    line = line_bytes.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    # Use time.time() for consistent timestamping
                    timestamp = time.time()
                    raw_message = parse_sbs_message(line, timestamp)

                    if raw_message:
                        await handle_message(raw_message, redis_client)

                except asyncio.IncompleteReadError:
                    logger.warning("Incomplete read from ADS-B source. Connection lost?")
                    break  # Break inner loop to reconnect
                except ConnectionResetError:
                    logger.warning("Connection reset by ADS-B source.")
                    break  # Break inner loop to reconnect
                except Exception:
                    logger.exception(f"Error processing line: '{line[:100]}...'")  # Log snippet
                    # Continue processing next line

        except ConnectionRefusedError:
            logger.error(f"Connection refused by {ADSB_HOST}:{ADSB_PORT}.")
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to {ADSB_HOST}:{ADSB_PORT}.")
        except OSError as e:
            logger.error(f"OS error connecting to {ADSB_HOST}:{ADSB_PORT}: {e}")
        except Exception:
            logger.exception("Unexpected error in ingest connection loop.")

        # Wait before attempting to reconnect
        logger.info(f"Waiting {RECONNECT_DELAY} seconds before reconnecting...")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(run_ingest_loop())
    except KeyboardInterrupt:
        logger.info("Ingest loop stopped by user.")

"""Main ADS-B ingest loop.

Connects to TCP source, parses messages, smooths data, and stores in Redis.
"""

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field

from backend.ingest.enrichment import (
    EnrichedData,
    RouteData,
    fetch_aeroapi_route,
    fetch_opensky_data,
)
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
    """Represents the smoothed state of an aircraft stored in Redis.

    Includes core position/velocity, a capped trail, and cached enrichment data.
    """

    hex_ident: str = Field(..., description="Aircraft ICAO hex identifier.")
    lat: float = Field(..., description="Smoothed latitude.")
    lon: float = Field(..., description="Smoothed longitude.")
    alt: float = Field(..., description="Smoothed altitude in feet.")
    lat_v: float = Field(..., description="Smoothed latitude velocity.")
    lon_v: float = Field(..., description="Smoothed longitude velocity.")
    alt_v: float = Field(..., description="Smoothed altitude velocity (fpm).")
    last_update_ts: float = Field(..., description="Timestamp of the last update.")
    trail: List[Tuple[float, float, float]] = Field(
        default_factory=list,
        description="List of recent (lat, lon, alt) tuples, capped at 30.",
    )
    callsign: Optional[str] = Field(None, description="Aircraft callsign (cached).")
    origin_country: Optional[str] = Field(
        None, description="Origin country based on ICAO24 (cached)."
    )
    category: Optional[int] = Field(None, description="Aircraft category code (cached).")
    # AeroAPI Enrichment fields (cached)
    origin: Optional[str] = Field(None, description="Origin airport ICAO (cached).")
    destination: Optional[str] = Field(None, description="Destination airport ICAO (cached).")
    # TODO: Add other fields like ground speed, track etc. later


# Runtime state (in-memory)
active_smoothers: Dict[str, PositionSmoother] = {}
last_timestamps: Dict[str, float] = {}


# --- Main Ingest Logic ---
async def handle_message(msg: RawMessage, redis_client: RedisClient) -> None:
    """Process a parsed RawMessage: enrich, update smoother, store in Redis."""
    if not msg.latitude or not msg.longitude or not msg.altitude:
        # logger.debug(f"Skipping message for {msg.hex_ident}: Missing position data.")
        return  # Skip messages without position

    hex_ident = msg.hex_ident
    current_time = msg.timestamp
    measurement = np.array([msg.latitude, msg.longitude, msg.altitude])
    redis_key = f"plane:{hex_ident}"

    # Try to get existing state first
    existing_state_dict = await redis_client.get_json(redis_key)
    existing_state: Optional[PlaneState] = (
        PlaneState(**existing_state_dict) if existing_state_dict else None
    )

    smoother = active_smoothers.get(hex_ident)
    enriched_data: Optional[EnrichedData] = None
    route_data: Optional[RouteData] = None

    if smoother is None:
        logger.info(f"Creating new smoother for {hex_ident}.")
        smoother = PositionSmoother(
            initial_pos=measurement,
            process_noise=KALMAN_PROCESS_NOISE,
            measurement_noise=KALMAN_MEASUREMENT_NOISE,
        )
        active_smoothers[hex_ident] = smoother
        last_timestamps[hex_ident] = current_time
        smoothed_state_vector = np.concatenate((measurement, np.zeros(3)))
        current_trail = [(measurement[0], measurement[1], measurement[2])]
        logger.info(f"Fetching enrichment data for new plane {hex_ident}.")
        enriched_data = await fetch_opensky_data(hex_ident, redis_client)
        route_data = await fetch_aeroapi_route(hex_ident, redis_client)
    else:
        last_time = last_timestamps.get(hex_ident, current_time)
        dt = max(0.01, current_time - last_time)

        try:
            smoother.predict(dt)
            smoother.update(measurement)
            smoothed_state_vector = smoother.state
            last_timestamps[hex_ident] = current_time
            # logger.debug(f"Updated smoother for {hex_ident}. dt={dt:.2f}s")

            # Manage the trail
            current_trail = existing_state.trail if existing_state else []
            new_point = (
                smoothed_state_vector[0],
                smoothed_state_vector[1],
                smoothed_state_vector[2],
            )
            current_trail.append(new_point)
            # Cap the trail at 30 points
            if len(current_trail) > 30:
                current_trail.pop(0)  # Remove the oldest point

            # Carry over existing enrichment data if available
            if existing_state:
                enriched_data = EnrichedData(
                    callsign=existing_state.callsign,
                    origin_country=existing_state.origin_country,
                    category=existing_state.category,
                )
                route_data = RouteData(
                    origin_icao=existing_state.origin,
                    destination_icao=existing_state.destination,
                )

        except np.linalg.LinAlgError as e:
            logger.error(f"Kalman filter error for {hex_ident}: {e}. Resetting smoother.")
            # Reset smoother on numerical instability
            del active_smoothers[hex_ident]
            del last_timestamps[hex_ident]
            return

    # Prepare data for Redis, including the updated trail and enrichment data
    plane_data = PlaneState(
        hex_ident=hex_ident,
        lat=smoothed_state_vector[0],
        lon=smoothed_state_vector[1],
        alt=smoothed_state_vector[2],
        lat_v=smoothed_state_vector[3],
        lon_v=smoothed_state_vector[4],
        alt_v=smoothed_state_vector[5],
        last_update_ts=current_time,
        trail=current_trail,
        callsign=enriched_data.callsign if enriched_data else None,
        origin_country=enriched_data.origin_country if enriched_data else None,
        category=enriched_data.category if enriched_data else None,
        origin=route_data.origin_icao if route_data else None,
        destination=route_data.destination_icao if route_data else None,
    )

    # Store in Redis
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

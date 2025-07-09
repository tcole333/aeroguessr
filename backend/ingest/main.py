"""Main ADS-B ingest loop.

Connects to TCP source, parses messages, smooths data, and stores in Redis.
"""

import asyncio
import importlib
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
# ADSB_HOST defaults to 127.0.0.1 to be explicit for the main connection loop.
# If FAKE_ADSB=1, the internal generator also uses 127.0.0.1.
ADSB_HOST = os.getenv("ADSB_HOST", "127.0.0.1")
ADSB_PORT = int(os.getenv("ADSB_PORT", 30003))
KALMAN_PROCESS_NOISE = float(os.getenv("KALMAN_PROCESS_NOISE", 0.5))
KALMAN_MEASUREMENT_NOISE = float(os.getenv("KALMAN_MEASUREMENT_NOISE", 10.0))
PLANE_TTL_SECONDS = int(os.getenv("PLANE_TTL_SECONDS", 300))
RECONNECT_DELAY = 5  # Seconds to wait before retrying connection

# --- Logging Setup ---
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
        description="List of recent (lat, lon, alt) tuples, capped at 10.",
    )
    callsign: Optional[str] = Field(None, description="Aircraft callsign (cached).")
    origin_country: Optional[str] = Field(
        None, description="Origin country based on ICAO24 (cached)."
    )
    category: Optional[int] = Field(None, description="Aircraft category code (cached).")
    # AeroAPI Enrichment fields (cached)
    origin: Optional[str] = Field(None, description="Origin airport ICAO (cached).")
    destination: Optional[str] = Field(None, description="Destination airport ICAO (cached).")
    # Signal quality tracking
    first_seen_ts: float = Field(
        default_factory=lambda: time.time(), description="Timestamp when plane was first detected."
    )
    update_count: int = Field(
        default=1, description="Number of position updates received for this plane."
    )
    # TODO: Add other fields like ground speed, track etc. later


# Runtime state (in-memory)
active_smoothers: Dict[str, PositionSmoother] = {}
last_timestamps: Dict[str, float] = {}


# --- Main Ingest Logic ---
async def handle_message(msg: RawMessage, redis_client: RedisClient) -> None:
    """Process a parsed RawMessage: enrich, update smoother, store in Redis."""
    if not msg.latitude or not msg.longitude or not msg.altitude:
        return  # Skip messages without position

    hex_ident = msg.hex_ident
    current_time = msg.timestamp
    measurement = np.array([msg.latitude, msg.longitude, msg.altitude])
    redis_key = f"plane:{hex_ident}"

    # Try to get existing state first using get_model utility
    existing_state: Optional[PlaneState] = await redis_client.get_model(redis_key, PlaneState)

    # === BEGIN ADDED LOGGING FOR EXISTING STATE ===
    if existing_state:
        logger.info(
            f"INGEST_MAIN: Loaded existing_state for {hex_ident} - Origin: "
            f"{existing_state.origin}, Destination: {existing_state.destination}, "
            f"Callsign: {existing_state.callsign}"
        )
    # === END ADDED LOGGING ===

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
            # Cap the trail at 10 points for shorter trails
            if len(current_trail) > 10:
                current_trail.pop(0)  # Remove the oldest point

            # === BEGIN ADDED LOGGING BEFORE CARRY OVER ===
            logger.info(
                f"INGEST_MAIN (Carry Over): Existing state for {hex_ident} before "
                f"constructing enrichment - Origin: {existing_state.origin}, Dest: "
                f"{existing_state.destination}"
            )
            # === END ADDED LOGGING BEFORE CARRY OVER ===
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
    # Handle signal quality tracking
    if existing_state:
        # Existing plane: increment update count, preserve first_seen_ts
        first_seen_ts = existing_state.first_seen_ts
        update_count = existing_state.update_count + 1
    else:
        # New plane: set first_seen_ts and initialize update count
        first_seen_ts = current_time
        update_count = 1

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
        first_seen_ts=first_seen_ts,
        update_count=update_count,
    )

    # === BEGIN RE-ADDED LOGGING ===
    if existing_state is None:  # This implies it's a new plane
        logger.info(
            f"INGEST_MAIN: Storing NEW PlaneState to Redis for {hex_ident}: "
            f"{plane_data.model_dump_json(indent=2)}"
        )
    else:  # This is for an existing plane update
        logger.debug(
            f"INGEST_MAIN: Storing UPDATED PlaneState to Redis for {hex_ident}: "
            f"{plane_data.model_dump_json(indent=2)}"
        )
    # === END RE-ADDED LOGGING ===

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

    host_to_connect = ADSB_HOST
    port_to_connect = ADSB_PORT
    server_task = None  # Define server_task in this scope

    if os.getenv("FAKE_ADSB") == "1":
        sample_path = os.getenv("FAKE_ADSB_FILE", "sample_data/sbs_parser_fixtures.sbs")
        # Explicitly use 127.0.0.1 for the internal generator and connection
        internal_gen_host = "127.0.0.1"
        internal_gen_port = ADSB_PORT  # Use the configured port from .env

        logger.info(
            "FAKE_ADSB=1: Starting internal sample generator from '%s' on %s:%s.",
            sample_path,
            internal_gen_host,
            internal_gen_port,
        )

        try:
            adsb_gen_mod = importlib.import_module("sample_data.adsb_generator")
        except ImportError:
            logger.error("Failed to import 'sample_data.adsb_generator'. Ensure it exists.")
            return  # Cannot proceed with FAKE_ADSB

        server_task = asyncio.create_task(
            adsb_gen_mod.run_server(
                filepath=sample_path,
                host=internal_gen_host,
                port=internal_gen_port,
                loop_forever=True,
                speed=float(os.getenv("FAKE_ADSB_SPEED", "1.0")),
            )
        )

        server_ready = False
        # Increased max_retries and added a slightly longer initial sleep
        await asyncio.sleep(0.1)  # Brief initial pause for task to start
        max_retries = 30  # e.g., 30 * 0.1s = 3 seconds total wait
        retry_delay = 0.1  # seconds

        for attempt in range(max_retries):
            try:
                logger.debug(
                    "Attempting to connect to internal generator (Attempt %d/%d)...",
                    attempt + 1,
                    max_retries,
                )
                conn_reader, conn_writer = await asyncio.open_connection(
                    internal_gen_host, internal_gen_port
                )
                conn_writer.close()
                await conn_writer.wait_closed()
                server_ready = True
                logger.info(
                    "Internal ADS-B generator is ready on %s:%s.",
                    internal_gen_host,
                    internal_gen_port,
                )
                host_to_connect = internal_gen_host
                port_to_connect = internal_gen_port
                break
            except ConnectionRefusedError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(
                        "Internal ADS-B generator failed to start/accept connections "
                        "on %s:%s after %d attempts.",
                        internal_gen_host,
                        internal_gen_port,
                        max_retries,
                    )
                    if server_task and not server_task.done():
                        server_task.cancel()
                    # Fallback to .env settings for ADSB_HOST/PORT, but log warning
                    logger.warning(
                        "FAKE_ADSB=1: Internal generator failed. Will attempt connection "
                        "using ADSB_HOST=%s, ADSB_PORT=%s from environment.",
                        ADSB_HOST,
                        ADSB_PORT,
                    )
            except Exception as e:
                logger.error(f"Unexpected error while waiting for internal generator: {e}")
                if server_task and not server_task.done():
                    server_task.cancel()
                break  # Break on other errors

        if not server_ready:
            logger.warning(
                "FAKE_ADSB=1: Proceeding with ADSB_HOST=%s, ADSB_PORT=%s "
                "(from .env or default) as internal generator check failed.",
                ADSB_HOST,
                ADSB_PORT,
            )
            # host_to_connect and port_to_connect are already set to ADSB_HOST/ADSB_PORT
            # by default

    while True:
        try:
            logger.info(f"Connecting to ADS-B source at {host_to_connect}:{port_to_connect}...")
            reader, writer = await asyncio.open_connection(host_to_connect, port_to_connect)
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

                    timestamp = time.time()
                    raw_message = parse_sbs_message(line, timestamp)

                    if raw_message:
                        await handle_message(raw_message, redis_client)

                except asyncio.IncompleteReadError:
                    logger.warning("Incomplete read from ADS-B source. Connection lost?")
                    break
                except ConnectionResetError:
                    logger.warning("Connection reset by ADS-B source.")
                    break
                except Exception:
                    logger.exception(f"Error processing line: '{line[:100]}...'")

        except ConnectionRefusedError:
            logger.error(f"Connection refused by {host_to_connect}:{port_to_connect}.")
        except asyncio.TimeoutError:
            logger.error(f"Connection timeout to {host_to_connect}:{port_to_connect}.")
        except OSError as e:
            logger.error(f"OS error connecting to {host_to_connect}:{port_to_connect}: {e}")
        except Exception:
            logger.exception("Unexpected error in ingest connection loop.")

        logger.info(f"Waiting {RECONNECT_DELAY} seconds before reconnecting...")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    try:
        asyncio.run(run_ingest_loop())
    except KeyboardInterrupt:
        logger.info("Ingest loop stopped by user.")
    except Exception:
        logger.exception("Unhandled exception in run_ingest_loop or asyncio.run")

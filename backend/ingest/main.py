"""Main ADS-B ingest loop.

Connects to TCP source, parses messages, smooths data, and stores in Redis.
Routes are resolved from an in-memory airport board, so handling a message
never makes a network call; the board refresher (started alongside the
reader) is the only part of the ingest that may spend AeroAPI credits.
"""

import asyncio
import importlib
import logging
import time
from typing import Dict, Optional

import numpy as np

from backend.ingest.airport_board import Route, RouteLookup
from backend.ingest.board_refresher import build_route_source
from backend.ingest.enrichment_config import EnrichmentConfig
from backend.ingest.parser import RawMessage, parse_sbs_message
from backend.ingest.smoother_enu import PositionSmootherENU
from backend.schemas.plane import PlaneState
from backend.services.ingest_heartbeat import start_heartbeat
from backend.settings import get_settings
from backend.utils.logging_config import configure_logging
from backend.utils.redis_async import RedisClient

# --- Configuration (backend/settings.py) ---
# With FAKE_ADSB=1 the internal generator listens on 127.0.0.1:ADSB_PORT.
ADSB_HOST = get_settings().adsb_host
ADSB_PORT = get_settings().adsb_port
# Origin of the smoother's local ENU frame, and where FAKE_ADSB's synthetic planes fly.
CENTER_LAT = get_settings().center_lat
CENTER_LON = get_settings().center_lon
PLANE_TTL_SECONDS = get_settings().plane_ttl_seconds
RECONNECT_DELAY = 5  # Seconds to wait before retrying connection

# --- Logging Setup ---
logger = logging.getLogger(__name__)


# Runtime state (in-memory)
active_smoothers: Dict[str, PositionSmootherENU] = {}
last_timestamps: Dict[str, float] = {}
callsign_cache: Dict[str, str] = {}  # hex_ident -> callsign
track_cache: Dict[str, float] = {}  # hex_ident -> track (degrees)


def _resolve_route(
    routes: RouteLookup,
    callsign: Optional[str],
    now: float,
    existing_state: Optional[PlaneState],
) -> Optional[Route]:
    """The board's route for this callsign, else the route already stored for it.

    Keeping the stored route means a plane does not lose it when its board row
    ages out while it is still in range. A new callsign never inherits one.
    """
    if callsign and callsign.strip():
        route = routes.lookup(callsign.strip(), now)
        if route is not None:
            return route
    if (
        existing_state is not None
        and existing_state.callsign == callsign
        and (existing_state.origin or existing_state.destination)
    ):
        return Route(
            origin_icao=existing_state.origin,
            destination_icao=existing_state.destination,
            operator=existing_state.operator,
        )
    return None


# --- Main Ingest Logic ---
async def handle_message(
    msg: RawMessage, redis_client: RedisClient, *, routes: RouteLookup
) -> None:
    """Process a parsed RawMessage: update smoother, resolve route, store in Redis.

    Routes come from ``routes``, an in-memory board, so this never makes a
    network call no matter how many planes or messages arrive.
    """
    # Handle MSG,1 (callsign only) messages - cache the callsign even without position
    if msg.callsign and msg.callsign.strip():
        callsign = msg.callsign.strip()
        callsign_cache[msg.hex_ident] = callsign
        logger.debug(f"Cached callsign for {msg.hex_ident}: {callsign}")

    # Cache track from MSG,2 and MSG,4 messages (raw ADS-B heading)
    if msg.track is not None:
        track_cache[msg.hex_ident] = msg.track
        logger.debug(f"Cached track for {msg.hex_ident}: {msg.track}°")

    if not msg.latitude or not msg.longitude or not msg.altitude:
        return  # Skip messages without position (but callsign was cached above)

    # Validate position is within reasonable bounds
    if not (-90 <= msg.latitude <= 90):
        logger.warning(f"Invalid latitude {msg.latitude} for {msg.hex_ident}")
        return
    if not (-180 <= msg.longitude <= 180):
        logger.warning(f"Invalid longitude {msg.longitude} for {msg.hex_ident}")
        return
    if not (-1000 <= msg.altitude <= 60000):  # Allow below sea level, max 60k feet
        logger.warning(f"Invalid altitude {msg.altitude} for {msg.hex_ident}")
        return

    hex_ident = msg.hex_ident
    current_time = msg.timestamp
    measurement = np.array([msg.latitude, msg.longitude, msg.altitude])
    measurement_tuple = (msg.latitude, msg.longitude, msg.altitude)
    redis_key = f"plane:{hex_ident}"

    # Try to get existing state first using get_model utility
    existing_state: Optional[PlaneState] = await redis_client.get_model(redis_key, PlaneState)

    smoother = active_smoothers.get(hex_ident)

    if smoother is None:
        logger.debug(f"Creating new smoother for {hex_ident}.")
        smoother = PositionSmootherENU(
            initial_pos_deg_ft=measurement_tuple,
            origin_ll=(CENTER_LAT, CENTER_LON),
        )
        active_smoothers[hex_ident] = smoother
        last_timestamps[hex_ident] = current_time
        smoothed_state_vector = smoother.state
        current_trail = [(measurement[0], measurement[1], measurement[2])]
    else:
        last_time = last_timestamps.get(hex_ident, current_time)
        dt = current_time - last_time

        # Validate time delta to prevent Kalman filter instability
        if dt < 0:
            logger.warning(f"Negative time delta for {hex_ident}: {dt}s. Skipping update.")
            return
        elif dt < 0.001:
            logger.debug(f"Very small time delta for {hex_ident}: {dt}s. Skipping update.")
            return
        elif dt > 30.0:
            logger.warning(f"Large time gap for {hex_ident}: {dt}s. Resetting smoother.")
            # Reset smoother for large gaps
            del active_smoothers[hex_ident]
            del last_timestamps[hex_ident]
            # Recursive call to create new smoother
            await handle_message(msg, redis_client, routes=routes)
            return

        # Cap maximum prediction time to prevent divergence
        dt = min(dt, 10.0)

        try:
            # Check for unrealistic position changes before updating
            if existing_state:
                # Calculate distance traveled
                lat_diff = measurement[0] - existing_state.lat
                lon_diff = measurement[1] - existing_state.lon

                # Rough distance calculation (degrees)
                distance_deg = np.sqrt(lat_diff**2 + lon_diff**2)

                # Maximum realistic speed:
                # - Commercial jets: up to 600 knots cruise
                # - Military/supersonic: up to 1200 knots
                # - At equator: 1 degree ≈ 60 nautical miles
                # - 1200 knots = 20 nm/min = 0.33 degrees/min = 0.0055 degrees/second
                # - But ADS-B data can have delays/batching, so we need a buffer
                # - Using 0.5 degrees/second to account for data delays and supersonic aircraft
                # - This allows up to ~1800 knots apparent speed to handle data bursts
                max_distance_deg = 0.5 * dt

                # EMERGENCY: Handle extreme jumps from corrupted ADS-B data
                # Seeing jumps of 25+ degrees (like Boston to Hawaii!)
                if distance_deg > 5.0:  # More than 5 degrees is definitely wrong
                    logger.error(
                        f"EXTREME position jump for {hex_ident}: "
                        f"{distance_deg:.4f} deg in {dt:.1f}s. Likely data corruption. "
                        f"Old: ({existing_state.lat:.4f}, {existing_state.lon:.4f}) "
                        f"New: ({measurement[0]:.4f}, {measurement[1]:.4f})"
                    )
                    return

                if distance_deg > max_distance_deg:
                    logger.warning(
                        f"Unrealistic position jump for {hex_ident}: "
                        f"{distance_deg:.4f} deg in {dt:.1f}s. Skipping update."
                    )
                    return

            smoother.predict(dt)
            smoother.update(measurement_tuple)
            smoothed_state_vector = smoother.state
            last_timestamps[hex_ident] = current_time

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

            if not existing_state:
                logger.warning(
                    f"INGEST_MAIN: Smoother exists for {hex_ident} but no Redis state found. "
                    f"Possible Redis expiration or data corruption."
                )

        except np.linalg.LinAlgError as e:
            logger.error(f"Kalman filter numerical instability for {hex_ident}: {e}")
            # Try to recover gracefully by using raw measurement
            smoothed_state_vector = np.concatenate((measurement, np.zeros(3)))

            # Reset the smoother but keep processing this update
            logger.info(f"Resetting smoother for {hex_ident} and using raw measurement")
            del active_smoothers[hex_ident]
            del last_timestamps[hex_ident]

            # Use existing trail or start new one
            current_trail = existing_state.trail if existing_state else []
            new_point = (measurement[0], measurement[1], measurement[2])
            current_trail.append(new_point)
            if len(current_trail) > 10:
                current_trail.pop(0)

    # Sanity check velocities - aircraft don't exceed ~0.01 deg/sec (about 600 knots)
    # If Kalman filter produces extreme velocities, clamp them
    max_velocity_deg_per_sec = 0.01  # ~600 knots at equator
    lat_v = smoothed_state_vector[3]
    lon_v = smoothed_state_vector[4]
    velocity_magnitude = np.sqrt(lat_v**2 + lon_v**2)

    if velocity_magnitude > max_velocity_deg_per_sec:
        # Scale down velocities to maximum
        scale_factor = max_velocity_deg_per_sec / velocity_magnitude
        smoothed_state_vector[3] *= scale_factor
        smoothed_state_vector[4] *= scale_factor
        logger.warning(
            f"Clamped extreme velocity for {hex_ident}: "
            f"{velocity_magnitude:.6f} deg/s -> {max_velocity_deg_per_sec:.6f} deg/s"
        )

    # Prepare data for Redis, including the updated trail and route
    # Handle signal quality tracking
    if existing_state:
        # Existing plane: increment update count, preserve first_seen_ts
        first_seen_ts = existing_state.first_seen_ts
        update_count = existing_state.update_count + 1
    else:
        # New plane: set first_seen_ts and initialize update count
        first_seen_ts = current_time
        update_count = 1

    # Determine callsign from: msg.callsign > cache > existing state
    resolved_callsign = (
        msg.callsign
        or callsign_cache.get(hex_ident)
        or (existing_state.callsign if existing_state else None)
    )

    # Determine track from: current message > cache > existing state
    resolved_track = (
        msg.track
        or track_cache.get(hex_ident)
        or (existing_state.track if existing_state else None)
    )

    route = _resolve_route(routes, resolved_callsign, current_time, existing_state)

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
        callsign=resolved_callsign,
        track=resolved_track,
        origin=route.origin_icao if route else None,
        destination=route.destination_icao if route else None,
        operator=route.operator if route else None,
        first_seen_ts=first_seen_ts,
        update_count=update_count,
    )
    logger.debug("Storing PlaneState for %s: %s", hex_ident, plane_data)

    # Store in Redis
    try:
        await redis_client.set_json(redis_key, plane_data, expire_seconds=PLANE_TTL_SECONDS)
    except Exception as e:
        logger.error(f"Failed to store {redis_key} in Redis: {e}")


def _log_refresher_exit(task: asyncio.Task) -> None:
    if not task.cancelled() and task.exception() is not None:
        logger.error("AeroAPI board refresher stopped", exc_info=task.exception())


async def run_ingest_loop() -> None:
    """Connect to ADS-B source and process messages indefinitely."""
    redis_client = RedisClient()
    settings = get_settings()
    config = EnrichmentConfig.from_env(settings.enrichment_environ())
    logger.info("Ingest loop starting. Connecting to Redis...")
    config.log_summary()
    # Test Redis connection early
    try:
        conn = await redis_client.get_connection()
        await conn.ping()
        logger.info("Redis connection successful.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}. Exiting.")
        return

    # /readyz relies on this heartbeat to know ingest is alive and on its feed.
    feed_status = start_heartbeat(redis_client)

    host_to_connect = ADSB_HOST
    port_to_connect = ADSB_PORT
    server_task = None  # Define server_task in this scope

    if config.fake_adsb:
        sample_path = settings.fake_adsb_file
        # Explicitly use 127.0.0.1 for the internal generator and connection
        internal_gen_host = "127.0.0.1"
        internal_gen_port = ADSB_PORT

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
                speed=settings.fake_adsb_speed,
                plane_count=settings.syn_plane_count,
                center=(CENTER_LAT, CENTER_LON),
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

    routes, board_refresher = build_route_source(config, redis_client)
    if board_refresher is not None:
        refresher_task = asyncio.create_task(board_refresher.run_forever(), name="board-refresher")
        refresher_task.add_done_callback(_log_refresher_exit)

    while True:
        try:
            logger.info(f"Connecting to ADS-B source at {host_to_connect}:{port_to_connect}...")
            reader, writer = await asyncio.open_connection(host_to_connect, port_to_connect)
            logger.info("Connected to ADS-B source.")
            feed_status.connected = True

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
                        await handle_message(raw_message, redis_client, routes=routes)

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

        feed_status.connected = False
        logger.info(f"Waiting {RECONNECT_DELAY} seconds before reconnecting...")
        await asyncio.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    configure_logging("ingest")
    try:
        asyncio.run(run_ingest_loop())
    except KeyboardInterrupt:
        logger.info("Ingest loop stopped by user.")
    except Exception:
        logger.exception("Unhandled exception in run_ingest_loop or asyncio.run")

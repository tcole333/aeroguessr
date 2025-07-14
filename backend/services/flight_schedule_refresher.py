"""Background service to periodically refresh FlightAware scheduled flight cache.

This service runs as a background task to ensure the flight schedule cache
stays fresh for accurate flight matching.
"""

import asyncio
import logging
import os

from backend.ingest.flightaware_scheduled import build_flight_schedule_cache
from backend.utils.redis_async import RedisClient

# --- Configuration ---
REFRESH_INTERVAL_HOURS = float(os.getenv("FLIGHT_SCHEDULE_REFRESH_HOURS", "6"))
AIRPORT_CODE = "KBOS"

# --- Logging Setup ---
logger = logging.getLogger(__name__)


async def refresh_flight_schedule_loop() -> None:
    """Continuously refresh flight schedule cache at configured intervals."""
    redis_client = RedisClient()

    logger.info(
        f"Starting flight schedule refresher for {AIRPORT_CODE} "
        f"(refresh every {REFRESH_INTERVAL_HOURS} hours)"
    )

    while True:
        try:
            # Force refresh the cache
            logger.info(f"Refreshing flight schedule cache for {AIRPORT_CODE}")
            cache = await build_flight_schedule_cache(redis_client, force_refresh=True)

            if cache:
                total_flights = len(cache.departures) + len(cache.arrivals)
                logger.info(
                    f"Successfully refreshed flight schedule: "
                    f"{len(cache.departures)} departures, {len(cache.arrivals)} arrivals "
                    f"({total_flights} total flights)"
                )
            else:
                logger.error("Failed to refresh flight schedule cache")

        except Exception as e:
            logger.error(f"Error refreshing flight schedule: {e}")

        # Wait for next refresh interval
        await asyncio.sleep(REFRESH_INTERVAL_HOURS * 3600)


def run_refresher() -> None:
    """Entry point for running the refresher as a standalone service."""
    try:
        asyncio.run(refresh_flight_schedule_loop())
    except KeyboardInterrupt:
        logger.info("Flight schedule refresher stopped by user")
    except Exception as e:
        logger.exception(f"Unhandled exception in flight schedule refresher: {e}")


if __name__ == "__main__":
    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    )
    run_refresher()

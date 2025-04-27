"""Integration tests for AeroAPI enrichment (requires live API key)."""

import logging
import os
from typing import Optional

import httpx  # Added httpx import
import pytest

# Module to test
from backend.ingest.enrichment import RouteData, fetch_aeroapi_route
from backend.utils.redis_async import RedisClient  # Use real Redis client

# Mark all tests in this module as async and integration tests
pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# --- Test Configuration ---

# TEST_LIVE_HEX_ID = "a835af" # Removed hardcoded ID
API_KEY_SET = bool(os.getenv("FLIGHTAWARE_API_KEY"))
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"  # Added OpenSky URL

# --- Logging Setup ---
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)  # Changed default level to INFO


# --- Helper to find a live aircraft ---
async def _find_live_hex_id() -> Optional[str]:
    """Queries OpenSky anonymously to find an active aircraft hex ID."""
    logger.info(f"Querying OpenSky ({OPENSKY_STATES_URL}) for live aircraft...")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPENSKY_STATES_URL)
            response.raise_for_status()
            data = response.json()
            if data and data.get("states"):
                for state in data["states"]:
                    # Check for hex, lat, lon, alt (indices 0, 6, 5, 7)
                    if (
                        state[0]
                        and state[5] is not None
                        and state[6] is not None
                        and state[7] is not None
                    ):
                        hex_id = state[0].lower().strip()
                        logger.info(f"Found potentially live aircraft: {hex_id}")
                        return hex_id
                logger.warning("OpenSky returned states, but none had full position data.")
            else:
                logger.warning("OpenSky returned no states.")
    except httpx.RequestError as e:
        logger.error(f"Error connecting to OpenSky to find live aircraft: {e}")
    except Exception as e:
        logger.error(f"Error parsing OpenSky response: {e}")
    return None


# --- Integration Test Cases ---


@pytest.mark.skipif(not API_KEY_SET, reason="FLIGHTAWARE_API_KEY not set in environment")
async def test_fetch_aeroapi_live() -> None:
    """Tests fetching route data from the live AeroAPI using a dynamically found hex ID."""

    live_hex_id = await _find_live_hex_id()
    if not live_hex_id:
        pytest.skip("Could not find a live aircraft hex ID via OpenSky to test AeroAPI.")

    logger.info(f"Attempting live AeroAPI fetch for dynamically found hex: {live_hex_id}")
    redis_client = RedisClient()  # Use the actual Redis client

    # Clear potential cache entry before test
    cache_key = f"aeroapi_route:{live_hex_id}"
    try:
        conn = await redis_client.get_connection()
        await conn.delete(cache_key)
        logger.debug(f"Cleared cache entry: {cache_key}")
    except Exception as e:
        logger.warning(f"Could not clear cache before test: {e}")

    try:
        result = await fetch_aeroapi_route(live_hex_id, redis_client)

        logger.info(f"Live AeroAPI fetch result for {live_hex_id}: {result}")

        # Basic assertions: Check type or None, ensure no unexpected exceptions
        assert result is None or isinstance(result, RouteData)

        if isinstance(result, RouteData):
            # Optional: Check if codes look like ICAO codes (e.g., 4 letters)
            if result.origin_icao:
                assert len(result.origin_icao) == 4 and result.origin_icao.isalpha()
            if result.destination_icao:
                assert len(result.destination_icao) == 4 and result.destination_icao.isalpha()
            logger.info(
                (
                    f"Successfully fetched and parsed: Origin={result.origin_icao}, "
                    f"Dest={result.destination_icao}"
                )
            )
        else:
            logger.warning(
                (
                    f"No route data returned for {live_hex_id}. This might be expected if "
                    f"flight info isn't in AeroAPI yet."
                )
            )

    except Exception as e:
        # Fail the test if any unexpected exception occurs during the fetch
        pytest.fail(f"fetch_aeroapi_route raised an unexpected exception: {e}")
    # No finally block needed as RedisClient manages its pool internally
    # finally:
    #     await redis_client.close_pool()

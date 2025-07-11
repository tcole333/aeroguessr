"""Fetches and caches supplementary aircraft data from OpenSky Network."""

import logging
import os
import random
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from backend.utils.redis_async import RedisClient

# --- Configuration ---
OPENSKY_USERNAME = os.getenv("OPENSKY_USERNAME")
OPENSKY_PASSWORD = os.getenv("OPENSKY_PASSWORD")
OPENSKY_API_URL = "https://opensky-network.org/api/states/all"
CACHE_TTL_SECONDS = 86400  # 24 hours

FLIGHTAWARE_API_KEY = os.getenv("FLIGHTAWARE_API_KEY")
AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AEROAPI_CACHE_TTL_SECONDS = 3600 * 6  # Cache route data for 6 hours

# Check if we're in synthetic mode
IS_FAKE_ADSB = os.getenv("FAKE_ADSB") == "1"

# --- Logging Setup ---
logger = logging.getLogger(__name__)


# --- Data Structures ---
class EnrichedData(BaseModel):
    """Represents cached supplementary data for an aircraft (from OpenSky)."""

    callsign: Optional[str] = Field(None, description="Aircraft callsign.")
    origin_country: Optional[str] = Field(None, description="Origin country based on ICAO24.")
    category: Optional[int] = Field(None, description="Aircraft category code (see OpenSky docs).")
    # TODO: Live Origin/Destination not available via free OpenSky states endpoint.
    # origin: Optional[str] = None
    # destination: Optional[str] = None
    # airline: Optional[str] = None # Could potentially be inferred from callsign


class RouteData(BaseModel):
    """Represents cached origin/destination data for a flight (from AeroAPI)."""

    origin_icao: Optional[str] = Field(None, description="Origin airport ICAO code.")
    destination_icao: Optional[str] = Field(None, description="Destination airport ICAO code.")


# --- Enrichment Logic: OpenSky (Callsign, etc.) ---
async def fetch_opensky_data(hex_ident: str, redis_client: RedisClient) -> Optional[EnrichedData]:
    """Fetches supplementary aircraft data (callsign, country, category) from cache or OpenSky."""
    cache_key = f"enrich_cache:{hex_ident}"

    # 1. Check cache
    try:
        cached_data: Optional[EnrichedData] = await redis_client.get_model(cache_key, EnrichedData)
        if cached_data:
            logger.debug(f"Cache hit for OpenSky enrichment data: {hex_ident}")
            return cached_data
    except Exception as e:
        logger.error(f"Redis error checking OpenSky enrichment cache for {hex_ident}: {e}")

    logger.debug(f"Cache miss for OpenSky enrichment data: {hex_ident}. Fetching from OpenSky.")

    # 2. Fetch from OpenSky API
    auth = (OPENSKY_USERNAME, OPENSKY_PASSWORD) if OPENSKY_USERNAME and OPENSKY_PASSWORD else None
    params = {"icao24": hex_ident}

    try:
        async with httpx.AsyncClient(auth=auth, timeout=10.0) as client:
            response = await client.get(OPENSKY_API_URL, params=params)
            response.raise_for_status()
            data = response.json()

            if data and data.get("states") and len(data["states"]) > 0:
                state_vector = data["states"][0]
                callsign = state_vector[1].strip() if state_vector[1] else None
                origin_country = state_vector[2]
                category = state_vector[17] if len(state_vector) > 17 else None

                enriched_data = EnrichedData(
                    callsign=callsign,
                    origin_country=origin_country,
                    category=category,
                )

                # 3. Store in cache
                try:
                    await redis_client.set_json(
                        cache_key, enriched_data, expire_seconds=CACHE_TTL_SECONDS
                    )
                    logger.info(f"Fetched and cached OpenSky enrichment data for {hex_ident}")
                except Exception as e:
                    logger.error(
                        f"Redis error caching OpenSky enrichment data for {hex_ident}: {e}"
                    )

                return enriched_data
            else:
                logger.warning(f"No state vector found in OpenSky response for {hex_ident}")
                return None

    except httpx.HTTPStatusError as e:
        # Suppress 403 errors in synthetic mode - they're expected
        if IS_FAKE_ADSB and e.response.status_code == 403:
            logger.debug(f"OpenSky API 403 for {hex_ident} (expected in synthetic mode)")
        else:
            logger.error(
                (
                    f"OpenSky API request failed for {hex_ident}: {e.response.status_code} - "
                    f"{e.response.text}"
                )
            )
        return None
    except httpx.RequestError as e:
        logger.error(f"Error connecting to OpenSky API for {hex_ident}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching OpenSky enrichment data for {hex_ident}: {e}")
        return None


# --- Enrichment Logic: AeroAPI (Origin/Destination) ---
async def fetch_aeroapi_route(hex_ident: str, redis_client: RedisClient) -> Optional[RouteData]:
    """Fetches flight origin/destination from cache or FlightAware AeroAPI.

    If FAKE_ADSB environment variable is set to "1", returns mock route data
    with Boston (KBOS) as either origin or destination.

    Uses the ICAO24 hex identifier to look up the flight.

    Args:
        hex_ident: The ICAO24 hex identifier of the aircraft.
        redis_client: An instance of RedisClient for caching.

    Returns:
        A RouteData object if data is found or fetched, otherwise None.
    """
    if os.getenv("FAKE_ADSB") == "1":
        logger.info(f"FAKE_ADSB active. Returning mock route data for {hex_ident}.")
        mock_airports = ["KLAX", "KJFK", "KORD", "KSFO", "KMIA", None]

        # Always make Boston the destination so synthetic planes can land and respawn
        other_airport = random.choice(mock_airports)
        origin_icao = other_airport
        destination_icao = "KBOS"

        # Ensure that origin and destination are not both None if one is KBOS
        if origin_icao is None and destination_icao == "KBOS":
            origin_icao = random.choice(
                [ap for ap in mock_airports if ap is not None and ap != "KBOS"]
            )
        elif destination_icao is None and origin_icao == "KBOS":
            destination_icao = random.choice(
                [ap for ap in mock_airports if ap is not None and ap != "KBOS"]
            )
        # Ensure origin and destination are not the same if both are not None
        elif origin_icao == destination_icao and origin_icao is not None:
            if origin_icao == "KBOS":  # if both are KBOS, change the other one
                destination_icao = random.choice([ap for ap in mock_airports if ap != "KBOS"])
            else:  # if both are some other airport, change one to KBOS (should not happen with
                # current logic but good failsafe)
                if random.choice([True, False]):
                    origin_icao = "KBOS"
                else:
                    destination_icao = "KBOS"

        # Final check if both became None (e.g. other_airport was None and
        #  it was assigned to the non-KBOS leg)
        # This ensures at least KBOS is present.
        if origin_icao is None and destination_icao is None:
            if random.choice([True, False]):
                origin_icao = "KBOS"
            else:
                destination_icao = "KBOS"

        mock_route = RouteData(origin_icao=origin_icao, destination_icao=destination_icao)
        logger.info(
            f"FAKE_ADSB: Generated mock route for {hex_ident}: "
            f"Origin: {mock_route.origin_icao}, Dest: {mock_route.destination_icao}"
        )
        return mock_route

    if not FLIGHTAWARE_API_KEY:
        logger.warning("FLIGHTAWARE_API_KEY not set. Skipping AeroAPI route lookup.")
        return None

    cache_key = f"aeroapi_route:{hex_ident}"

    # 1. Check cache
    try:
        cached_data: Optional[RouteData] = await redis_client.get_model(cache_key, RouteData)
        if cached_data:
            logger.debug(f"Cache hit for AeroAPI route data: {hex_ident}")
            return cached_data
    except Exception as e:
        logger.error(f"Redis error checking AeroAPI route cache for {hex_ident}: {e}")

    logger.debug(f"Cache miss for AeroAPI route data: {hex_ident}. Fetching from AeroAPI.")

    # 2. Fetch from AeroAPI
    api_url = f"{AEROAPI_BASE_URL}/flights/{hex_ident}"
    headers = {"x-apikey": FLIGHTAWARE_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url, headers=headers)

            # Handle not found specifically - might mean flight is old or ident invalid
            if response.status_code == 404:
                logger.warning(
                    f"AeroAPI returned 404 (Not Found) for flight {hex_ident}. "
                    "Possibly no current flight data."
                )
                # TODO: Consider caching this negative result for a short period?
                return None

            response.raise_for_status()  # Raise for other 4xx/5xx errors
            data = response.json()

            # AeroAPI returns a list of flights matching the ident
            if data and isinstance(data.get("flights"), list) and len(data["flights"]) > 0:
                # Assuming the first flight is the most relevant/current one
                # This might need refinement based on actual API behavior and flight status
                flight_info = data["flights"][0]
                origin_icao = flight_info.get("origin", {}).get("code_icao")
                destination_icao = flight_info.get("destination", {}).get("code_icao")

                if not origin_icao and not destination_icao:
                    logger.warning(
                        f"AeroAPI response for {hex_ident} missing origin/destination codes."
                    )
                    return None  # Or cache negative result?

                route_data = RouteData(
                    origin_icao=origin_icao,
                    destination_icao=destination_icao,
                )

                # 3. Store in cache
                try:
                    await redis_client.set_json(
                        cache_key, route_data, expire_seconds=AEROAPI_CACHE_TTL_SECONDS
                    )
                    logger.info(f"Fetched and cached AeroAPI route data for {hex_ident}")
                except Exception as e:
                    logger.error(f"Redis error caching AeroAPI route data for {hex_ident}: {e}")

                return route_data
            else:
                logger.warning(f"No flight data found in AeroAPI response for {hex_ident}")
                return None

    except httpx.HTTPStatusError as e:
        logger.error(
            f"AeroAPI request failed for {hex_ident}: {e.response.status_code} - {e.response.text}"
        )
        return None
    except httpx.RequestError as e:
        logger.error(f"Error connecting to AeroAPI for {hex_ident}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching AeroAPI route data for {hex_ident}: {e}")
        return None

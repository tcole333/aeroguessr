"""FlightAware AeroAPI scheduled flights fetching and caching.

This module fetches scheduled departures and arrivals from FlightAware AeroAPI
for Boston Logan (KBOS) and builds lookup tables for efficient flight matching.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field

from backend.utils.redis_async import RedisClient

# --- Configuration ---
FLIGHTAWARE_API_KEY = os.getenv("FLIGHTAWARE_API_KEY")
AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
AIRPORT_CODE = "KBOS"  # Boston Logan
SCHEDULED_FLIGHTS_CACHE_TTL = 12 * 3600  # 12 hours
RESULTS_PER_PAGE = 15  # FlightAware returns 15 results per page

# --- Logging Setup ---
logger = logging.getLogger(__name__)


# --- Data Structures ---
class ScheduledFlight(BaseModel):
    """Represents a scheduled flight from FlightAware API."""

    ident: str = Field(..., description="Flight callsign/ident (e.g., UAL123)")
    registration: Optional[str] = Field(None, description="Aircraft registration (e.g., N12345)")
    origin_icao: str = Field(..., description="Origin airport ICAO code")
    destination_icao: str = Field(..., description="Destination airport ICAO code")
    scheduled_departure: Optional[datetime] = Field(None, description="Scheduled departure time")
    scheduled_arrival: Optional[datetime] = Field(None, description="Scheduled arrival time")
    aircraft_type: Optional[str] = Field(None, description="Aircraft type code")


class FlightScheduleCache(BaseModel):
    """Cached flight schedule data with lookup tables."""

    last_updated: datetime = Field(..., description="When this cache was last updated")
    departures: List[ScheduledFlight] = Field(default_factory=list)
    arrivals: List[ScheduledFlight] = Field(default_factory=list)
    # Lookup tables built from the flight lists
    callsign_lookup: Dict[str, ScheduledFlight] = Field(
        default_factory=dict, description="Lookup by flight callsign"
    )
    registration_lookup: Dict[str, ScheduledFlight] = Field(
        default_factory=dict, description="Lookup by aircraft registration"
    )


class FlightAwareScheduledClient:
    """Client for fetching scheduled flights from FlightAware AeroAPI."""

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or FLIGHTAWARE_API_KEY
        if not self.api_key:
            logger.warning("FLIGHTAWARE_API_KEY not set")
        self.headers = {"x-apikey": self.api_key} if self.api_key else {}

    async def fetch_scheduled_departures(
        self, airport: str, max_pages: int = 2
    ) -> List[ScheduledFlight]:
        """Fetch scheduled departures for an airport.

        Args:
            airport: Airport ICAO code (e.g., KBOS)
            max_pages: Maximum number of pages to fetch (15 flights per page)

        Returns:
            List of scheduled departure flights
        """
        if not self.api_key:
            logger.error("Cannot fetch scheduled departures without API key")
            return []

        flights = []
        url = f"{AEROAPI_BASE_URL}/airports/{airport}/flights/scheduled_departures"

        # Calculate time window: current time to 12 hours from now
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=12)

        params = {
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "max_pages": max_pages,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                for flight_data in data.get("scheduled_departures", []):
                    try:
                        flight = ScheduledFlight(
                            ident=flight_data.get("ident", ""),
                            registration=flight_data.get("registration"),
                            origin_icao=flight_data.get("origin", {}).get("code_icao", airport),
                            destination_icao=flight_data.get("destination", {}).get(
                                "code_icao", ""
                            ),
                            scheduled_departure=flight_data.get("scheduled_off"),
                            scheduled_arrival=flight_data.get("scheduled_on"),
                            aircraft_type=flight_data.get("aircraft_type"),
                        )
                        flights.append(flight)
                    except Exception as e:
                        logger.error(f"Error parsing departure flight data: {e}")
                        continue

                logger.info(f"Fetched {len(flights)} scheduled departures from {airport}")
                return flights

        except httpx.HTTPStatusError as e:
            logger.error(f"FlightAware API error fetching departures: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error fetching scheduled departures: {e}")
            return []

    async def fetch_scheduled_arrivals(
        self, airport: str, max_pages: int = 2
    ) -> List[ScheduledFlight]:
        """Fetch scheduled arrivals for an airport.

        Args:
            airport: Airport ICAO code (e.g., KBOS)
            max_pages: Maximum number of pages to fetch (15 flights per page)

        Returns:
            List of scheduled arrival flights
        """
        if not self.api_key:
            logger.error("Cannot fetch scheduled arrivals without API key")
            return []

        flights = []
        url = f"{AEROAPI_BASE_URL}/airports/{airport}/flights/scheduled_arrivals"

        # Calculate time window: current time to 12 hours from now
        start_time = datetime.utcnow()
        end_time = start_time + timedelta(hours=12)

        params = {
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "max_pages": max_pages,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                for flight_data in data.get("scheduled_arrivals", []):
                    try:
                        flight = ScheduledFlight(
                            ident=flight_data.get("ident", ""),
                            registration=flight_data.get("registration"),
                            origin_icao=flight_data.get("origin", {}).get("code_icao", ""),
                            destination_icao=flight_data.get("destination", {}).get(
                                "code_icao", airport
                            ),
                            scheduled_departure=flight_data.get("scheduled_off"),
                            scheduled_arrival=flight_data.get("scheduled_on"),
                            aircraft_type=flight_data.get("aircraft_type"),
                        )
                        flights.append(flight)
                    except Exception as e:
                        logger.error(f"Error parsing arrival flight data: {e}")
                        continue

                logger.info(f"Fetched {len(flights)} scheduled arrivals to {airport}")
                return flights

        except httpx.HTTPStatusError as e:
            logger.error(f"FlightAware API error fetching arrivals: {e.response.status_code}")
            return []
        except Exception as e:
            logger.error(f"Error fetching scheduled arrivals: {e}")
            return []


async def build_flight_schedule_cache(
    redis_client: RedisClient, force_refresh: bool = False
) -> Optional[FlightScheduleCache]:
    """Build or retrieve cached flight schedule with lookup tables.

    Args:
        redis_client: Redis client for caching
        force_refresh: Force refresh even if cache exists

    Returns:
        FlightScheduleCache with populated lookup tables
    """
    cache_key = f"flight_schedule:{AIRPORT_CODE}"

    # Check cache first unless force refresh
    if not force_refresh:
        try:
            cached_data = await redis_client.get_model(cache_key, FlightScheduleCache)
            if cached_data:
                # Check if cache is still fresh (less than 12 hours old)
                age = datetime.utcnow() - cached_data.last_updated
                if age < timedelta(hours=12):
                    logger.info(f"Using cached flight schedule (age: {age})")
                    return cached_data
        except Exception as e:
            logger.error(f"Error retrieving cached flight schedule: {e}")

    # Fetch fresh data
    logger.info(f"Fetching fresh flight schedule for {AIRPORT_CODE}")
    client = FlightAwareScheduledClient()

    # Fetch both departures and arrivals
    departures = await client.fetch_scheduled_departures(AIRPORT_CODE, max_pages=3)
    arrivals = await client.fetch_scheduled_arrivals(AIRPORT_CODE, max_pages=3)

    # Build lookup tables
    # IMPORTANT: When same callsign appears in both departures and arrivals,
    # we need to pick the most relevant one. We prefer the flight that's
    # scheduled closer to the current time.
    callsign_lookup: Dict[str, ScheduledFlight] = {}
    registration_lookup: Dict[str, ScheduledFlight] = {}
    now = datetime.utcnow()

    for flight in departures + arrivals:
        # Add to callsign lookup - pick the flight scheduled closer to now
        if flight.ident:
            existing = callsign_lookup.get(flight.ident)
            if existing is None:
                callsign_lookup[flight.ident] = flight
            else:
                # Both exist - pick the one scheduled closer to now
                existing_time = existing.scheduled_departure or existing.scheduled_arrival
                new_time = flight.scheduled_departure or flight.scheduled_arrival
                if existing_time and new_time:
                    # Pick whichever is closer to now (past or future)
                    existing_diff = abs((existing_time - now).total_seconds())
                    new_diff = abs((new_time - now).total_seconds())
                    if new_diff < existing_diff:
                        callsign_lookup[flight.ident] = flight
                        logger.debug(
                            f"Callsign {flight.ident}: preferring flight scheduled at "
                            f"{new_time} over {existing_time} (closer to now)"
                        )

        # Add to registration lookup - same logic
        if flight.registration:
            existing = registration_lookup.get(flight.registration)
            if existing is None:
                registration_lookup[flight.registration] = flight
            else:
                existing_time = existing.scheduled_departure or existing.scheduled_arrival
                new_time = flight.scheduled_departure or flight.scheduled_arrival
                if existing_time and new_time:
                    existing_diff = abs((existing_time - now).total_seconds())
                    new_diff = abs((new_time - now).total_seconds())
                    if new_diff < existing_diff:
                        registration_lookup[flight.registration] = flight

    # Create cache object
    cache = FlightScheduleCache(
        last_updated=datetime.utcnow(),
        departures=departures,
        arrivals=arrivals,
        callsign_lookup=callsign_lookup,
        registration_lookup=registration_lookup,
    )

    # Store in Redis
    try:
        await redis_client.set_json(cache_key, cache, expire_seconds=SCHEDULED_FLIGHTS_CACHE_TTL)
        logger.info(
            f"Cached flight schedule with {len(departures)} departures and {len(arrivals)} arrivals"
        )
    except Exception as e:
        logger.error(f"Error caching flight schedule: {e}")

    return cache


async def lookup_flight_by_callsign(
    callsign: str, redis_client: RedisClient
) -> Optional[Tuple[str, str]]:
    """Look up flight origin/destination by callsign.

    Args:
        callsign: Flight callsign (e.g., UAL123)
        redis_client: Redis client

    Returns:
        Tuple of (origin_icao, destination_icao) if found
    """
    cache = await build_flight_schedule_cache(redis_client)
    if not cache:
        return None

    flight = cache.callsign_lookup.get(callsign)
    if flight:
        logger.debug(f"Found flight {callsign} in schedule cache")
        return (flight.origin_icao, flight.destination_icao)

    return None


async def lookup_flight_by_registration(
    registration: str, redis_client: RedisClient
) -> Optional[Tuple[str, str]]:
    """Look up flight origin/destination by aircraft registration.

    Args:
        registration: Aircraft registration (e.g., N12345)
        redis_client: Redis client

    Returns:
        Tuple of (origin_icao, destination_icao) if found
    """
    cache = await build_flight_schedule_cache(redis_client)
    if not cache:
        return None

    flight = cache.registration_lookup.get(registration)
    if flight:
        logger.debug(f"Found flight with registration {registration} in schedule cache")
        return (flight.origin_icao, flight.destination_icao)

    return None

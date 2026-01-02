"""Enhanced flight enrichment with multi-tier lookup system.

This module implements an improved enrichment strategy that:
1. First attempts to match by callsign against scheduled flights (fast, cached)
2. Falls back to hex->registration conversion and registration lookup (fast, cached)
3. Falls back to direct AeroAPI query by callsign (slower, real-time)
4. Falls back to direct AeroAPI query by registration (slower, real-time)
5. Maintains backward compatibility with existing RouteData model

The direct AeroAPI queries are the key improvement for GA (general aviation) traffic
that isn't in the scheduled flights database.
"""

import logging
import os
import random
from typing import Optional

import httpx
from pydantic import BaseModel

from backend.ingest.enrichment import RouteData
from backend.ingest.flightaware_scheduled import (
    lookup_flight_by_callsign,
    lookup_flight_by_registration,
)
from backend.ingest.hex_to_registration import hex_to_registration
from backend.utils.redis_async import RedisClient


class RouteLookupMeta(BaseModel):
    """Metadata about a route lookup attempt for debugging/display purposes."""

    detail: Optional[str] = None  # e.g., "no_callsign", "api_error", "not_found"
    source: Optional[str] = None  # e.g., "schedule", "direct_api", "cache"
    callsign_used: Optional[str] = None
    registration_used: Optional[str] = None


# --- Configuration ---
ROUTE_CACHE_TTL_SECONDS = 3600 * 6  # 6 hours for positive results
OPERATOR_CACHE_TTL_SECONDS = 3600 * 24 * 7  # 7 days for operator names (rarely change)
IS_FAKE_ADSB = os.getenv("FAKE_ADSB") == "1"

FLIGHTAWARE_API_KEY = os.getenv("FLIGHTAWARE_API_KEY")
AEROAPI_BASE_URL = "https://aeroapi.flightaware.com/aeroapi"

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- In-memory operator cache (supplement to Redis) ---
_operator_cache: dict[str, str] = {}

# --- Monitoring Metrics ---
# These counters help track match rates for monitoring
match_stats = {
    "total_requests": 0,
    "callsign_matches": 0,
    "registration_matches": 0,
    "direct_api_matches": 0,
    "no_matches": 0,
    "cache_hits": 0,
}


async def _lookup_operator_name(operator_icao: str) -> Optional[str]:
    """Look up operator short name from ICAO code, with caching.

    Uses FlightAware's /operators/{icao} endpoint to get the airline name.
    Results are cached in memory since airline names rarely change.

    Args:
        operator_icao: ICAO airline code (e.g., "UAL" for United)

    Returns:
        Operator short name (e.g., "United") or None if not found
    """
    if not operator_icao:
        return None

    # Check in-memory cache first
    if operator_icao in _operator_cache:
        return _operator_cache[operator_icao]

    if not FLIGHTAWARE_API_KEY:
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AEROAPI_BASE_URL}/operators/{operator_icao}",
                headers={"x-apikey": FLIGHTAWARE_API_KEY},
                timeout=10.0,
            )

            if response.status_code == 404:
                logger.debug(f"Operator not found: {operator_icao}")
                return None

            response.raise_for_status()
            data = response.json()

            # Prefer shortname, fall back to callsign or name
            short_name = data.get("shortname") or data.get("callsign") or data.get("name")

            if short_name:
                _operator_cache[operator_icao] = short_name
                logger.debug(f"Cached operator: {operator_icao} -> {short_name}")
                return short_name

            return None

    except httpx.HTTPStatusError as e:
        logger.warning(f"Operator lookup error for {operator_icao}: {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"Operator lookup failed for {operator_icao}: {e}")
        return None


async def fetch_route_data_v2(
    hex_ident: str,
    redis_client: RedisClient,
    callsign: Optional[str] = None,
) -> Optional[RouteData]:
    """Enhanced route data fetching with multi-tier lookup strategy.

    This function implements a four-tier matching strategy:
    1. If callsign is provided, attempt to match against scheduled flights (fast)
    2. Convert hex to registration and lookup in scheduled flights (fast)
    3. Direct AeroAPI query by callsign (slower but catches GA traffic)
    4. Direct AeroAPI query by registration (slower but catches GA traffic)

    Args:
        hex_ident: The ICAO24 hex identifier of the aircraft
        redis_client: Redis client for caching
        callsign: Optional flight callsign (e.g., "UAL123")

    Returns:
        RouteData object with origin_icao and destination_icao, or None if no match
    """
    match_stats["total_requests"] += 1

    # Handle synthetic mode with mock data
    if IS_FAKE_ADSB:
        logger.info(f"FAKE_ADSB active. Returning mock route data for {hex_ident}.")
        return _generate_mock_route_data(hex_ident)

    # Check positive cache first
    cache_key = f"aeroapi_route_v2:{hex_ident}"
    try:
        cached_data: Optional[RouteData] = await redis_client.get_model(cache_key, RouteData)
        if cached_data:
            logger.debug(f"Cache hit for route data v2: {hex_ident}")
            match_stats["cache_hits"] += 1
            return cached_data
    except Exception as e:
        logger.error(f"Redis error checking route cache v2 for {hex_ident}: {e}")

    logger.debug(f"Cache miss for route data v2: {hex_ident}. Starting multi-tier lookup.")

    # Clean up callsign
    clean_callsign = callsign.strip() if callsign else None

    # Get registration for later use
    registration = await hex_to_registration(hex_ident, redis_client)
    if registration:
        logger.debug(f"Got registration {registration} for hex {hex_ident}")

    # Metadata key for debugging
    meta_key = f"aeroapi_route_v2_meta:{hex_ident}"

    # Strategy 1: Try callsign lookup in scheduled flights (fast, cached)
    if clean_callsign:
        logger.debug(f"Strategy 1: Checking scheduled flights by callsign {clean_callsign}")
        route_tuple = await lookup_flight_by_callsign(clean_callsign, redis_client)
        if route_tuple:
            origin_icao, destination_icao = route_tuple
            route_data = RouteData(origin_icao=origin_icao, destination_icao=destination_icao)
            logger.info(
                f"[Schedule/Callsign] Match for {hex_ident}/{clean_callsign}: "
                f"{origin_icao} -> {destination_icao}"
            )
            match_stats["callsign_matches"] += 1
            await _cache_route_data(cache_key, route_data, redis_client)
            meta = RouteLookupMeta(source="schedule", callsign_used=clean_callsign)
            await _cache_meta(meta_key, meta, redis_client)
            return route_data

    # Strategy 2: Try registration lookup in scheduled flights (fast, cached)
    if registration:
        logger.debug(f"Strategy 2: Checking scheduled flights by registration {registration}")
        route_tuple = await lookup_flight_by_registration(registration, redis_client)
        if route_tuple:
            origin_icao, destination_icao = route_tuple
            route_data = RouteData(origin_icao=origin_icao, destination_icao=destination_icao)
            logger.info(
                f"[Schedule/Registration] Match for {hex_ident}/{registration}: "
                f"{origin_icao} -> {destination_icao}"
            )
            match_stats["registration_matches"] += 1
            await _cache_route_data(cache_key, route_data, redis_client)
            meta = RouteLookupMeta(source="schedule", registration_used=registration)
            await _cache_meta(meta_key, meta, redis_client)
            return route_data

    # Strategy 3: Direct AeroAPI query by callsign (slower, but catches GA traffic)
    if clean_callsign:
        logger.debug(f"Strategy 3: Direct AeroAPI query by callsign {clean_callsign}")
        route_data = await _query_aeroapi_direct(clean_callsign)
        if route_data:
            logger.info(
                f"[AeroAPI/Callsign] Match for {hex_ident}/{clean_callsign}: "
                f"{route_data.origin_icao} -> {route_data.destination_icao}"
            )
            match_stats["direct_api_matches"] += 1
            await _cache_route_data(cache_key, route_data, redis_client)
            meta = RouteLookupMeta(source="direct_api", callsign_used=clean_callsign)
            await _cache_meta(meta_key, meta, redis_client)
            return route_data

    # Strategy 4: Direct AeroAPI query by registration (slower, catches GA)
    if registration:
        logger.debug(f"Strategy 4: Direct AeroAPI query by registration {registration}")
        route_data = await _query_aeroapi_direct(registration)
        if route_data:
            logger.info(
                f"[AeroAPI/Registration] Match for {hex_ident}/{registration}: "
                f"{route_data.origin_icao} -> {route_data.destination_icao}"
            )
            match_stats["direct_api_matches"] += 1
            await _cache_route_data(cache_key, route_data, redis_client)
            meta = RouteLookupMeta(source="direct_api", registration_used=registration)
            await _cache_meta(meta_key, meta, redis_client)
            return route_data

    # No match found - rely on backoff retry instead of negative caching
    # Determine why we couldn't find data (for debugging)
    if not clean_callsign and not registration:
        detail = "no_callsign_or_registration"
    elif not clean_callsign:
        detail = "no_callsign"
    else:
        detail = "not_found"

    logger.debug(
        f"No route data found for {hex_ident} "
        f"(callsign: {clean_callsign or 'none'}, registration: {registration or 'unknown'})"
    )
    match_stats["no_matches"] += 1

    # Store metadata about the failed lookup (for debugging)
    meta = RouteLookupMeta(
        detail=detail,
        callsign_used=clean_callsign,
        registration_used=registration,
    )
    await _cache_meta(meta_key, meta, redis_client)

    # Log match statistics periodically
    if match_stats["total_requests"] % 100 == 0:
        _log_match_statistics()

    return None


async def _query_aeroapi_direct(ident: str) -> Optional[RouteData]:
    """Query AeroAPI directly for flight route data.

    This is the fallback for flights not in the scheduled flights database,
    particularly useful for GA (general aviation) traffic.

    Args:
        ident: Flight identifier (callsign or registration, e.g., "UAL123" or "N12345")

    Returns:
        RouteData if flight is found, None otherwise
    """
    if not FLIGHTAWARE_API_KEY:
        logger.warning("FLIGHTAWARE_API_KEY not set. Skipping direct AeroAPI query.")
        return None

    api_url = f"{AEROAPI_BASE_URL}/flights/{ident}"
    headers = {"x-apikey": FLIGHTAWARE_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(api_url, headers=headers)

            # Handle not found - flight doesn't exist or has no data
            if response.status_code == 404:
                logger.debug(f"AeroAPI 404 for {ident} - no flight data available")
                return None

            response.raise_for_status()
            data = response.json()

            # AeroAPI returns a list of flights matching the ident
            flights = data.get("flights", [])
            if not flights:
                logger.debug(f"AeroAPI returned empty flights list for {ident}")
                return None

            # Find the most relevant flight (prefer in-progress or most recent)
            best_flight = None
            for flight in flights:
                # Prefer flights that are currently in progress
                if flight.get("progress_percent") is not None:
                    progress = flight.get("progress_percent", 0)
                    if 0 < progress < 100:
                        best_flight = flight
                        break

                # Otherwise take the first one with valid origin/destination
                origin = flight.get("origin", {}).get("code_icao")
                destination = flight.get("destination", {}).get("code_icao")
                if origin or destination:
                    if best_flight is None:
                        best_flight = flight

            if not best_flight:
                logger.debug(f"No suitable flight found in AeroAPI response for {ident}")
                return None

            origin_icao = best_flight.get("origin", {}).get("code_icao")
            destination_icao = best_flight.get("destination", {}).get("code_icao")

            if not origin_icao and not destination_icao:
                logger.debug(f"AeroAPI flight {ident} missing origin/destination")
                return None

            # Extract and look up operator name
            operator_icao = best_flight.get("operator_icao") or best_flight.get("operator")
            operator_name = await _lookup_operator_name(operator_icao) if operator_icao else None

            return RouteData(
                origin_icao=origin_icao,
                destination_icao=destination_icao,
                operator=operator_name,
            )

    except httpx.HTTPStatusError as e:
        logger.error(f"AeroAPI error for {ident}: {e.response.status_code}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Connection error to AeroAPI for {ident}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error querying AeroAPI for {ident}: {e}")
        return None


async def _cache_route_data(
    cache_key: str, route_data: RouteData, redis_client: RedisClient
) -> None:
    """Cache route data in Redis.

    Args:
        cache_key: Redis key for caching
        route_data: Route data to cache
        redis_client: Redis client
    """
    try:
        await redis_client.set_json(cache_key, route_data, expire_seconds=ROUTE_CACHE_TTL_SECONDS)
        logger.debug(f"Cached route data for {cache_key}")
    except Exception as e:
        logger.error(f"Redis error caching route data: {e}")


async def _cache_meta(meta_key: str, meta: RouteLookupMeta, redis_client: RedisClient) -> None:
    """Cache lookup metadata for debugging/display purposes.

    Args:
        meta_key: Redis key for metadata
        meta: RouteLookupMeta object
        redis_client: Redis client
    """
    try:
        await redis_client.set_json(meta_key, meta, expire_seconds=ROUTE_CACHE_TTL_SECONDS)
        logger.debug(f"Cached lookup metadata for {meta_key}")
    except Exception as e:
        logger.error(f"Redis error caching metadata: {e}")


def _generate_mock_route_data(hex_ident: str) -> RouteData:
    """Generate mock route data for synthetic testing.

    Maintains same behavior as original enrichment.py for compatibility.

    Args:
        hex_ident: Hex identifier (used for logging)

    Returns:
        Mock RouteData with Boston as origin or destination
    """
    mock_airports = ["KLAX", "KJFK", "KORD", "KSFO", "KMIA", None]
    mock_operators = ["United", "Delta", "American", "JetBlue", "Southwest", None]

    # Always make Boston the destination so synthetic planes can land and respawn
    other_airport = random.choice(mock_airports)
    mock_operator = random.choice(mock_operators)
    origin_icao = other_airport
    destination_icao = "KBOS"

    # Ensure valid origin/destination combinations
    if origin_icao is None and destination_icao == "KBOS":
        origin_icao = random.choice([ap for ap in mock_airports if ap is not None and ap != "KBOS"])
    elif destination_icao is None and origin_icao == "KBOS":
        destination_icao = random.choice(
            [ap for ap in mock_airports if ap is not None and ap != "KBOS"]
        )
    elif origin_icao == destination_icao and origin_icao is not None:
        if origin_icao == "KBOS":
            destination_icao = random.choice([ap for ap in mock_airports if ap != "KBOS"])
        else:
            if random.choice([True, False]):
                origin_icao = "KBOS"
            else:
                destination_icao = "KBOS"

    # Final fallback
    if origin_icao is None and destination_icao is None:
        if random.choice([True, False]):
            origin_icao = "KBOS"
        else:
            destination_icao = "KBOS"

    mock_route = RouteData(
        origin_icao=origin_icao, destination_icao=destination_icao, operator=mock_operator
    )
    logger.info(
        f"FAKE_ADSB: Generated mock route for {hex_ident}: "
        f"Origin: {mock_route.origin_icao}, Dest: {mock_route.destination_icao}, "
        f"Operator: {mock_route.operator}"
    )
    return mock_route


def _log_match_statistics() -> None:
    """Log current match rate statistics."""
    total = match_stats["total_requests"]
    if total == 0:
        return

    callsign_rate = (match_stats["callsign_matches"] / total) * 100
    registration_rate = (match_stats["registration_matches"] / total) * 100
    direct_api_rate = (match_stats["direct_api_matches"] / total) * 100
    no_match_rate = (match_stats["no_matches"] / total) * 100
    cache_hit_rate = (match_stats["cache_hits"] / total) * 100

    # Calculate total success rate (any match type)
    success_rate = callsign_rate + registration_rate + direct_api_rate + cache_hit_rate

    logger.info(
        f"Route enrichment v2 statistics (n={total}): "
        f"SUCCESS={success_rate:.1f}% "
        f"[Schedule/Callsign: {callsign_rate:.1f}%, "
        f"Schedule/Reg: {registration_rate:.1f}%, "
        f"DirectAPI: {direct_api_rate:.1f}%, "
        f"Cache: {cache_hit_rate:.1f}%] "
        f"NoMatch: {no_match_rate:.1f}%"
    )


def get_match_statistics() -> dict:
    """Get current match statistics for monitoring.

    Returns:
        Dictionary with match statistics and rates
    """
    total = match_stats["total_requests"]
    if total == 0:
        return {
            "total_requests": 0,
            "rates": {
                "callsign_match_rate": 0.0,
                "registration_match_rate": 0.0,
                "direct_api_match_rate": 0.0,
                "no_match_rate": 0.0,
                "cache_hit_rate": 0.0,
                "success_rate": 0.0,
            },
            "counts": match_stats.copy(),
        }

    callsign_rate = (match_stats["callsign_matches"] / total) * 100
    registration_rate = (match_stats["registration_matches"] / total) * 100
    direct_api_rate = (match_stats["direct_api_matches"] / total) * 100
    cache_hit_rate = (match_stats["cache_hits"] / total) * 100
    success_rate = callsign_rate + registration_rate + direct_api_rate + cache_hit_rate

    return {
        "total_requests": total,
        "rates": {
            "callsign_match_rate": callsign_rate,
            "registration_match_rate": registration_rate,
            "direct_api_match_rate": direct_api_rate,
            "no_match_rate": (match_stats["no_matches"] / total) * 100,
            "cache_hit_rate": cache_hit_rate,
            "success_rate": success_rate,
        },
        "counts": match_stats.copy(),
    }


def reset_match_statistics() -> None:
    """Reset match statistics counters."""
    global match_stats
    match_stats = {
        "total_requests": 0,
        "callsign_matches": 0,
        "registration_matches": 0,
        "direct_api_matches": 0,
        "no_matches": 0,
        "cache_hits": 0,
    }
    logger.info("Match statistics reset")

"""Enhanced flight enrichment with dual-lookup matching system.

This module implements an improved enrichment strategy that:
1. First attempts to match by callsign against scheduled flights
2. Falls back to hex->registration conversion and registration lookup
3. Maintains backward compatibility with existing RouteData model
"""

import logging
import os
import random
from typing import Optional

from backend.ingest.enrichment import RouteData
from backend.ingest.flightaware_scheduled import (
    lookup_flight_by_callsign,
    lookup_flight_by_registration,
)
from backend.ingest.hex_to_registration import hex_to_registration
from backend.utils.redis_async import RedisClient

# --- Configuration ---
ROUTE_CACHE_TTL_SECONDS = 3600 * 6  # 6 hours - same as original
IS_FAKE_ADSB = os.getenv("FAKE_ADSB") == "1"

# --- Logging Setup ---
logger = logging.getLogger(__name__)

# --- Monitoring Metrics ---
# These counters help track match rates for monitoring
match_stats = {
    "total_requests": 0,
    "callsign_matches": 0,
    "registration_matches": 0,
    "no_matches": 0,
    "cache_hits": 0,
}


async def fetch_route_data_v2(
    hex_ident: str,
    redis_client: RedisClient,
    callsign: Optional[str] = None,
) -> Optional[RouteData]:
    """Enhanced route data fetching with dual-lookup strategy.

    This function implements a two-tier matching strategy:
    1. If callsign is provided, attempt to match against scheduled flights
    2. If no callsign match, convert hex to registration and lookup by registration

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

    # Check cache first
    cache_key = f"aeroapi_route_v2:{hex_ident}"
    try:
        cached_data: Optional[RouteData] = await redis_client.get_model(cache_key, RouteData)
        if cached_data:
            logger.debug(f"Cache hit for route data v2: {hex_ident}")
            match_stats["cache_hits"] += 1
            return cached_data
    except Exception as e:
        logger.error(f"Redis error checking route cache v2 for {hex_ident}: {e}")

    logger.debug(f"Cache miss for route data v2: {hex_ident}. Attempting dual-lookup.")

    # Strategy 1: Try callsign lookup if provided
    if callsign:
        callsign = callsign.strip()
        if callsign:
            logger.debug(f"Attempting callsign lookup for {callsign}")
            route_tuple = await lookup_flight_by_callsign(callsign, redis_client)
            if route_tuple:
                origin_icao, destination_icao = route_tuple
                route_data = RouteData(
                    origin_icao=origin_icao,
                    destination_icao=destination_icao,
                )
                logger.info(
                    f"Callsign match found for {hex_ident}/{callsign}: "
                    f"{origin_icao} -> {destination_icao}"
                )
                match_stats["callsign_matches"] += 1
                await _cache_route_data(cache_key, route_data, redis_client)
                return route_data

    # Strategy 2: Convert hex to registration and lookup
    logger.debug(f"Attempting hex->registration lookup for {hex_ident}")
    registration = await hex_to_registration(hex_ident, redis_client)
    if registration:
        logger.debug(f"Got registration {registration} for hex {hex_ident}")
        route_tuple = await lookup_flight_by_registration(registration, redis_client)
        if route_tuple:
            origin_icao, destination_icao = route_tuple
            route_data = RouteData(
                origin_icao=origin_icao,
                destination_icao=destination_icao,
            )
            logger.info(
                f"Registration match found for {hex_ident}/{registration}: "
                f"{origin_icao} -> {destination_icao}"
            )
            match_stats["registration_matches"] += 1
            await _cache_route_data(cache_key, route_data, redis_client)
            return route_data

    # No match found
    logger.warning(
        f"No route data found for {hex_ident} "
        f"(callsign: {callsign or 'none'}, registration: {registration or 'unknown'})"
    )
    match_stats["no_matches"] += 1

    # Log match statistics periodically
    if match_stats["total_requests"] % 100 == 0:
        _log_match_statistics()

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


def _generate_mock_route_data(hex_ident: str) -> RouteData:
    """Generate mock route data for synthetic testing.

    Maintains same behavior as original enrichment.py for compatibility.

    Args:
        hex_ident: Hex identifier (used for logging)

    Returns:
        Mock RouteData with Boston as origin or destination
    """
    mock_airports = ["KLAX", "KJFK", "KORD", "KSFO", "KMIA", None]

    # Always make Boston the destination so synthetic planes can land and respawn
    other_airport = random.choice(mock_airports)
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

    mock_route = RouteData(origin_icao=origin_icao, destination_icao=destination_icao)
    logger.info(
        f"FAKE_ADSB: Generated mock route for {hex_ident}: "
        f"Origin: {mock_route.origin_icao}, Dest: {mock_route.destination_icao}"
    )
    return mock_route


def _log_match_statistics() -> None:
    """Log current match rate statistics."""
    total = match_stats["total_requests"]
    if total == 0:
        return

    callsign_rate = (match_stats["callsign_matches"] / total) * 100
    registration_rate = (match_stats["registration_matches"] / total) * 100
    no_match_rate = (match_stats["no_matches"] / total) * 100
    cache_hit_rate = (match_stats["cache_hits"] / total) * 100

    logger.info(
        f"Route enrichment v2 statistics (n={total}): "
        f"Callsign matches: {callsign_rate:.1f}%, "
        f"Registration matches: {registration_rate:.1f}%, "
        f"No matches: {no_match_rate:.1f}%, "
        f"Cache hits: {cache_hit_rate:.1f}%"
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
                "no_match_rate": 0.0,
                "cache_hit_rate": 0.0,
            },
            "counts": match_stats.copy(),
        }

    return {
        "total_requests": total,
        "rates": {
            "callsign_match_rate": (match_stats["callsign_matches"] / total) * 100,
            "registration_match_rate": (match_stats["registration_matches"] / total) * 100,
            "no_match_rate": (match_stats["no_matches"] / total) * 100,
            "cache_hit_rate": (match_stats["cache_hits"] / total) * 100,
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
        "no_matches": 0,
        "cache_hits": 0,
    }
    logger.info("Match statistics reset")

"""ICAO hex code to aircraft registration conversion.

This module provides multiple methods to convert ICAO 24-bit hex codes to
aircraft registration numbers, with fallback strategies for reliability.
"""

import logging
import re
from typing import Optional

import httpx

from backend.utils.redis_async import RedisClient

# --- Configuration ---
HEXDB_API_URL = "https://hexdb.io/api/v1/aircraft"
HEXDB_CACHE_TTL = 7 * 24 * 3600  # 7 days - registration rarely changes
HEX_TO_REG_CACHE_PREFIX = "hex_to_reg"

# --- Logging Setup ---
logger = logging.getLogger(__name__)


def us_hex_to_registration(hex_code: str) -> Optional[str]:
    """Convert US aircraft ICAO hex code to N-number registration.

    US aircraft have ICAO hex codes in the range A00001-ADF7C7.
    Algorithm based on FAA allocation scheme.

    Args:
        hex_code: ICAO 24-bit hex code (e.g., "A1B2C3")

    Returns:
        US N-number registration (e.g., "N12345") or None if not US aircraft
    """
    hex_code = hex_code.upper()

    # Check if it's a US aircraft (starts with 'A')
    if not hex_code.startswith("A"):
        return None

    try:
        # Convert hex to decimal
        hex_int = int(hex_code, 16)

        # US aircraft offset (0xA00001 = 10485761)
        us_base = 0xA00001

        # Check if within US range (up to 0xADF7C7 = 11401159)
        if hex_int < us_base or hex_int > 0xADF7C7:
            return None

        # Calculate offset from base
        offset = hex_int - us_base + 1

        # N-numbers 1-99999 are numeric only
        if offset <= 99999:
            return f"N{offset}"

        # For offset > 99999, use alphanumeric encoding
        # This is a simplified version - full algorithm is more complex
        # but covers most common cases
        offset -= 99999

        # Convert to base-36 style encoding for suffix
        suffix = ""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # Note: I, O excluded
        while offset > 0:
            offset -= 1
            suffix = alphabet[offset % 24] + suffix
            offset //= 24

        # Construct registration with appropriate numeric prefix
        if len(suffix) == 1:
            return f"N{suffix}"
        elif len(suffix) == 2:
            # Two letter suffix gets single digit prefix
            digit = (hex_int - us_base) // 100000 % 10
            return f"N{digit}{suffix}"
        else:
            # Longer suffixes - this is simplified
            return f"N{suffix}"

    except Exception as e:
        logger.error(f"Error converting US hex {hex_code}: {e}")
        return None


async def fetch_hexdb_registration(
    hex_code: str, redis_client: Optional[RedisClient] = None
) -> Optional[str]:
    """Fetch aircraft registration from hexdb.io API.

    Args:
        hex_code: ICAO 24-bit hex code
        redis_client: Optional Redis client for caching

    Returns:
        Aircraft registration or None if not found
    """
    hex_code = hex_code.upper()
    cache_key = f"{HEX_TO_REG_CACHE_PREFIX}:hexdb:{hex_code}"

    # Check cache if Redis client provided
    if redis_client:
        try:
            cached_reg = await redis_client.get_string(cache_key)
            if cached_reg:
                logger.debug(f"Cache hit for hexdb registration: {hex_code} -> {cached_reg}")
                return cached_reg
        except Exception as e:
            logger.error(f"Error checking hexdb cache: {e}")

    # Fetch from API
    url = f"{HEXDB_API_URL}/{hex_code}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)

            if response.status_code == 404:
                logger.debug(f"hexdb.io: No data for {hex_code}")
                return None

            response.raise_for_status()
            data = response.json()

            registration = data.get("Registration")
            if registration:
                logger.info(f"hexdb.io: Found registration {registration} for {hex_code}")

                # Cache the result
                if redis_client:
                    try:
                        await redis_client.set_string(
                            cache_key, registration, expire_seconds=HEXDB_CACHE_TTL
                        )
                    except Exception as e:
                        logger.error(f"Error caching hexdb registration: {e}")

                return registration

            logger.warning(f"hexdb.io: No registration in response for {hex_code}")
            return None

    except httpx.HTTPStatusError as e:
        logger.error(f"hexdb.io API error: {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Error fetching from hexdb.io: {e}")
        return None


async def hex_to_registration(
    hex_code: str, redis_client: Optional[RedisClient] = None
) -> Optional[str]:
    """Convert ICAO hex code to aircraft registration using multiple methods.

    Tries in order:
    1. US algorithmic conversion (for US aircraft)
    2. hexdb.io API lookup (international coverage)

    Args:
        hex_code: ICAO 24-bit hex code
        redis_client: Optional Redis client for caching

    Returns:
        Aircraft registration or None if conversion fails
    """
    if not hex_code or not re.match(r"^[0-9A-Fa-f]{6}$", hex_code):
        logger.warning(f"Invalid hex code format: {hex_code}")
        return None

    hex_code = hex_code.upper()

    # Try US conversion first (fast, no API call)
    if hex_code.startswith("A"):
        registration = us_hex_to_registration(hex_code)
        if registration:
            logger.debug(f"US algorithm: {hex_code} -> {registration}")
            return registration

    # Fall back to hexdb.io for international aircraft
    registration = await fetch_hexdb_registration(hex_code, redis_client)
    if registration:
        return registration

    logger.warning(f"Could not convert hex {hex_code} to registration")
    return None


# Utility function for testing/validation
def validate_registration(registration: str) -> bool:
    """Validate aircraft registration format.

    Args:
        registration: Aircraft registration to validate

    Returns:
        True if registration appears valid
    """
    if not registration or len(registration) < 2:
        return False

    # Common registration patterns
    patterns = [
        r"^N[0-9]{1,5}[A-Z]{0,2}$",  # US N-numbers
        r"^[A-Z]-[A-Z]{4}$",  # Many countries (e.g., G-ABCD)
        r"^[A-Z]{2}-[A-Z]{3}$",  # Some countries (e.g., OO-ABC)
        r"^[A-Z]{1,2}[0-9]{3,5}$",  # Various formats
    ]

    return any(re.match(pattern, registration.upper()) for pattern in patterns)

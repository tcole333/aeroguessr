import logging
from typing import Tuple

# Use geopy for distance calculation
# from geopy.distance import geodesic
# use internal helpers
from backend.utils.airport_db import get_coords

# Distance helper – calculate haversine distance between two coordinate tuples.
# NOTE: We intentionally defer importing ``haversine_km`` until runtime inside
# ``calculate_distance_km`` to allow tests (or callers) to monkey-patch
# ``backend.utils.geo.haversine_km`` and have that patch respected.

logger = logging.getLogger(__name__)

# Placeholder types - replace with actual Airport model later
AirportCode = str
AirportCoords = Tuple[float, float]  # (latitude, longitude)


def calculate_exact_score(correct_code: AirportCode, guessed_code: AirportCode) -> int:
    """
    Calculates the score for Exact mode.

    Args:
        correct_code: The correct airport IATA/ICAO code.
        guessed_code: The player's guessed airport IATA/ICAO code.

    Returns:
        100 points if the guess is correct (case-insensitive), 0 otherwise.
        Also handles IATA/ICAO code equivalence (e.g., JFK = KJFK).
    """
    correct_upper = correct_code.upper()
    guessed_upper = guessed_code.upper()

    # Direct match
    if correct_upper == guessed_upper:
        return 100

    # Check if both codes refer to the same airport coordinates
    correct_coords = get_airport_coords(correct_upper)
    guessed_coords = get_airport_coords(guessed_upper)

    if correct_coords and guessed_coords and correct_coords == guessed_coords:
        logger.info(f"Airport code normalization match: '{guessed_code}' -> '{correct_code}'")
        return 100

    return 0


def get_airport_coords(code: AirportCode) -> AirportCoords | None:
    """Wrapper around airport_db for backwards-compat."""
    return get_coords(code)


# ---------------------------------------------------------------------------
# Distance helper
# ---------------------------------------------------------------------------


def calculate_distance_km(coords1: AirportCoords, coords2: AirportCoords) -> float:
    """Return great-circle distance between two airports.

    A thin wrapper around :pyfunc:`backend.utils.geo.haversine_km` that accepts
    coordinates as ``(lat, lon)`` tuples – convenient for tests and reuse.

    Args:
        coords1: Latitude/longitude tuple of the first coordinate.
        coords2: Latitude/longitude tuple of the second coordinate.

    Returns:
        Distance in kilometres as a float.
    """

    # Local import so that any patching of ``backend.utils.geo.haversine_km``
    # after module import time is picked up.
    from backend.utils.geo import haversine_km

    # Tests expect the function to be called with two coordinate tuples.
    return haversine_km(coords1, coords2)


def calculate_distance_score(correct_code: AirportCode, guessed_code: AirportCode) -> int:
    """
    Calculates the score for Distance mode.

    Args:
        correct_code: The correct airport IATA/ICAO code.
        guessed_code: The player's guessed airport IATA/ICAO code.

    Returns:
        Score based on distance: max(0, 100 - distance_km / 10).
        Returns 0 if either airport code is invalid or coords cannot be found.
    """
    correct_coords = get_airport_coords(correct_code)
    guessed_coords = get_airport_coords(guessed_code)

    if not correct_coords or not guessed_coords:
        logger.warning(
            f"Could not find coordinates for scoring: "
            f"Correct='{correct_code}' ({correct_coords}), "
            f"Guessed='{guessed_code}' ({guessed_coords})"
        )
        return 0

    if correct_coords == guessed_coords:
        return 100  # Exact match still gets full points

    # Use the wrapper so that our tests can easily patch distance calculations
    distance_km = calculate_distance_km(correct_coords, guessed_coords)

    score = max(0, 100 - (distance_km / 10))
    return int(round(score))


# Example usage:
# score_exact = calculate_exact_score("BOS", "bos") # Should be 100
# score_dist = calculate_distance_score("BOS", "JFK") # Should be < 100

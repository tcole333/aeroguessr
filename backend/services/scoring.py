import logging
from typing import Tuple

# Use geopy for distance calculation
from geopy.distance import geodesic

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
    """
    if correct_code.upper() == guessed_code.upper():
        return 100
    return 0


def get_airport_coords(airport_code: AirportCode) -> AirportCoords | None:
    """
    Placeholder function to retrieve airport coordinates.

    TODO: Implement actual lookup using cached airport data (e.g., from Redis).

    Args:
        airport_code: The IATA/ICAO code of the airport.

    Returns:
        A tuple (latitude, longitude) or None if not found.
    """
    # Replace with actual data loading/lookup
    mock_airports = {
        "BOS": (42.3656, -71.0096),  # Boston Logan
        "JFK": (40.6413, -73.7781),  # JFK New York
        "LAX": (33.9416, -118.4085),  # Los Angeles
        "LHR": (51.4700, -0.4543),  # London Heathrow
        "CDG": (49.0097, 2.5479),  # Charles de Gaulle, Paris
    }
    return mock_airports.get(airport_code.upper())


def calculate_distance_km(coords1: AirportCoords, coords2: AirportCoords) -> float:
    """
    Calculates the geodesic distance between two coordinates in kilometers.

    Uses the geopy library for accurate calculation.

    Args:
        coords1: Tuple (latitude, longitude) for the first point.
        coords2: Tuple (latitude, longitude) for the second point.

    Returns:
        The distance in kilometers.
    """
    try:
        distance = geodesic(coords1, coords2).km
        return distance
    except ValueError as e:
        # geopy raises ValueError for invalid coordinates
        logger.error(f"Invalid coordinates for distance calculation: {coords1}, {coords2} - {e}")
        # Return a large distance or raise? Returning large distance scores as 0.
        return float("inf")
    except Exception as e:
        # Catch other potential errors from geopy
        logger.error(f"Error calculating geodesic distance: {e}", exc_info=True)
        return float("inf")


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

    distance_km = calculate_distance_km(correct_coords, guessed_coords)

    score = max(0, 100 - (distance_km / 10))
    # Return score as integer
    return int(round(score))


# Example usage:
# score_exact = calculate_exact_score("BOS", "bos") # Should be 100
# score_dist = calculate_distance_score("BOS", "JFK") # Should be < 100

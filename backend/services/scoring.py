"""Score a guessed airport against a round's answer."""

import logging
from dataclasses import dataclass

from backend.schemas.core import ScoringMode
from backend.utils.airport_db import resolve_airport
from backend.utils.geo import haversine_km

logger = logging.getLogger(__name__)

MAX_POINTS = 100
KM_PER_POINT = 10  # Distance mode loses one point per 10 km (0 points from 1,000 km)


@dataclass(frozen=True)
class GuessScore:
    """Points for one guess and, in Distance mode, how far off it was.

    ``distance_km`` is None in Exact mode and whenever either airport is not
    in the dataset; it is 0.0 only when the guess names the answer airport.
    """

    points: int
    distance_km: float | None


def points_for_distance(distance_km: float) -> int:
    """Return Distance-mode points: ``round(max(0, 100 - km / 10))``."""
    return int(round(max(0.0, MAX_POINTS - distance_km / KM_PER_POINT)))


def score_guess(
    mode: ScoringMode, correct_code: str | None, guessed_code: str | None
) -> GuessScore:
    """Score ``guessed_code`` against ``correct_code``; either may be IATA or ICAO."""
    correct = resolve_airport(correct_code)
    guessed = resolve_airport(guessed_code)
    if correct is None or guessed is None:
        logger.warning(
            "Cannot score guess: answer %r resolved=%s, guess %r resolved=%s",
            correct_code,
            correct is not None,
            guessed_code,
            guessed is not None,
        )
        return GuessScore(points=0, distance_km=None)

    is_same_airport = correct.icao == guessed.icao
    if mode == ScoringMode.EXACT:
        return GuessScore(points=MAX_POINTS if is_same_airport else 0, distance_km=None)

    if is_same_airport:
        return GuessScore(points=MAX_POINTS, distance_km=0.0)
    distance_km = haversine_km(correct.coords, guessed.coords)
    return GuessScore(points=points_for_distance(distance_km), distance_km=distance_km)

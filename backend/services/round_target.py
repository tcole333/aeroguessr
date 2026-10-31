"""Decide whether a plane can be played and which end of its route is the answer.

Every round is about the monitored airport (KBOS by default): players guess
where a departing flight is going or where an arriving flight came from. The
answer must be in the airport dataset, otherwise no guess could ever score.

This is the single place that rule lives; plane selection uses it to accept or
reject a plane, and anything that flags planes as playable should use it too.
"""

from dataclasses import dataclass
from enum import Enum

from backend.schemas.plane import GuessDirection
from backend.settings import get_settings
from backend.utils.airport_db import resolve_airport, same_airport


def monitored_airport_icao() -> str:
    """Return the airport rounds are about (``MONITORED_AIRPORT_ICAO``, default KBOS)."""
    return get_settings().monitored_airport_icao


class RouteProblem(str, Enum):
    """Why a plane cannot be played."""

    NOT_MONITORED = "not_monitored"  # Neither end is the monitored airport (overhead flight)
    MISSING_ANSWER = "missing_answer"  # The end players would guess is unknown
    UNKNOWN_ANSWER_AIRPORT = "unknown_answer_airport"  # The answer is not in the dataset


@dataclass(frozen=True)
class RoundTarget:
    """The airport players would guess for a plane, or why there is none.

    ``guess_direction`` and ``answer_code`` are set whenever the plane touches
    the monitored airport, including when the answer is unknown or unscorable,
    so callers can say which airport is the problem.
    """

    guess_direction: GuessDirection | None
    answer_code: str | None
    problem: RouteProblem | None

    @property
    def is_playable(self) -> bool:
        return self.problem is None


def resolve_round_target(
    origin: str | None, destination: str | None, monitored_airport: str
) -> RoundTarget:
    """Return the round target for a plane flying ``origin`` -> ``destination``.

    A departure from the monitored airport is guessed by destination; an arrival
    by origin. When both ends are the monitored airport, the destination wins.
    """
    if same_airport(origin, monitored_airport):
        direction: GuessDirection = "destination"
        answer = destination
    elif same_airport(destination, monitored_airport):
        direction = "origin"
        answer = origin
    else:
        return RoundTarget(None, None, RouteProblem.NOT_MONITORED)

    if not answer:
        return RoundTarget(direction, None, RouteProblem.MISSING_ANSWER)
    if resolve_airport(answer) is None:
        return RoundTarget(direction, answer, RouteProblem.UNKNOWN_ANSWER_AIRPORT)
    return RoundTarget(direction, answer, None)

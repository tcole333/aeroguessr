"""Scoring behaviour against real airports from the committed dataset."""

import pytest

from backend.ingest.airport_board import FAKE_ORIGINS, FakeAirportBoard
from backend.schemas.core import ScoringMode
from backend.services.round_target import resolve_round_target
from backend.services.scoring import GuessScore, points_for_distance, score_guess
from backend.utils.airport_db import resolve_airport

# FAKE_ADSB answers are ICAO codes, while the autocomplete submits IATA codes.
DEMO_ANSWERS_WITH_IATA_GUESS = [
    ("KLAX", "LAX"),
    ("KJFK", "JFK"),
    ("KORD", "ORD"),
    ("KSFO", "SFO"),
    ("KMIA", "MIA"),
]


@pytest.mark.parametrize("mode", list(ScoringMode))
@pytest.mark.parametrize("answer, guess", DEMO_ANSWERS_WITH_IATA_GUESS)
def test_iata_guess_of_icao_answer_scores_full_points(
    mode: ScoringMode, answer: str, guess: str
) -> None:
    assert score_guess(mode, answer, guess).points == 100


@pytest.mark.parametrize("mode", list(ScoringMode))
def test_icao_guess_of_icao_answer_scores_full_points(mode: ScoringMode) -> None:
    assert score_guess(mode, "KORD", "KORD").points == 100


def test_guess_codes_ignore_case_and_whitespace() -> None:
    assert score_guess(ScoringMode.EXACT, "KORD", " ord ").points == 100


def test_exact_mode_awards_nothing_for_a_different_airport_in_the_same_city() -> None:
    assert score_guess(ScoringMode.EXACT, "KJFK", "LGA").points == 0


def test_exact_mode_reports_no_distance() -> None:
    assert score_guess(ScoringMode.EXACT, "KJFK", "JFK").distance_km is None


def test_distance_mode_same_airport_is_zero_km_and_full_points() -> None:
    assert score_guess(ScoringMode.DISTANCE, "KSFO", "SFO") == GuessScore(100, 0.0)


def test_distance_mode_nearby_guess_scores_partial_points() -> None:
    result = score_guess(ScoringMode.DISTANCE, "KPVD", "BOS")

    assert 75 < result.distance_km < 82
    assert result.points == 92


def test_distance_mode_guess_beyond_1000_km_scores_zero() -> None:
    result = score_guess(ScoringMode.DISTANCE, "KJFK", "ORD")

    assert 1150 < result.distance_km < 1220
    assert result.points == 0


@pytest.mark.parametrize("mode", list(ScoringMode))
@pytest.mark.parametrize(
    "answer, guess",
    [
        ("KJFK", "ZZZ"),  # unknown guess
        ("KMVY", "JFK"),  # answer missing from the dataset
        ("KMVY", "KMVY"),  # both missing: must not look like an exact match
        ("", ""),
        (None, None),
    ],
)
def test_unresolvable_airport_scores_nothing_and_reports_no_distance(
    mode: ScoringMode, answer: str | None, guess: str | None
) -> None:
    assert score_guess(mode, answer, guess) == GuessScore(0, None)


@pytest.mark.parametrize(
    "distance_km, points",
    [(0.0, 100), (78.8, 92), (990.0, 1), (1000.0, 0), (2150.0, 0)],
)
def test_points_for_distance(distance_km: float, points: int) -> None:
    assert points_for_distance(distance_km) == points


# --- Demo mode: every route the fake board hands out can be played and scored --- #


@pytest.mark.parametrize("mode", list(ScoringMode))
@pytest.mark.parametrize("origin_icao", FAKE_ORIGINS)
def test_correct_iata_guess_for_every_demo_origin_scores_full_points(
    mode: ScoringMode, origin_icao: str
) -> None:
    """Demo planes fly from FAKE_ORIGINS; the autocomplete submits the IATA code."""
    origin = resolve_airport(origin_icao)
    assert origin is not None and origin.iata, f"{origin_icao} is missing from the dataset"

    assert score_guess(mode, origin_icao, origin.iata).points == 100


def test_every_fake_board_route_is_a_playable_round() -> None:
    board = FakeAirportBoard("KBOS")
    routes = [
        board.lookup(f"{airline}{n}", now=0.0) for airline in ("AAL", "JBU") for n in range(200)
    ]

    origins = set()
    for route in routes:
        assert route is not None
        target = resolve_round_target(route.origin_icao, route.destination_icao, "KBOS")
        assert target.is_playable, route
        assert (target.guess_direction, target.answer_code) == ("origin", route.origin_icao)
        origins.add(route.origin_icao)
    assert origins == set(FAKE_ORIGINS)

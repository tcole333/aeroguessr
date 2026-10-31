"""Which planes can be played, and which airport players guess for them."""

import pytest

from backend.services.round_target import (
    RoundTarget,
    RouteProblem,
    monitored_airport_icao,
    resolve_round_target,
)

KBOS = "KBOS"


@pytest.mark.parametrize(
    "origin, destination, expected",
    [
        ("KBOS", "KJFK", RoundTarget("destination", "KJFK", None)),
        ("KJFK", "KBOS", RoundTarget("origin", "KJFK", None)),
        # IATA codes from a route source still name the monitored airport.
        ("BOS", "JFK", RoundTarget("destination", "JFK", None)),
        # A flight that returns to the monitored airport is guessed by destination.
        ("KBOS", "KBOS", RoundTarget("destination", "KBOS", None)),
    ],
)
def test_flights_touching_the_monitored_airport_are_playable(
    origin: str, destination: str, expected: RoundTarget
) -> None:
    target = resolve_round_target(origin, destination, KBOS)

    assert (target, target.is_playable) == (expected, True)


@pytest.mark.parametrize("origin", ["KLAX", "KJFK", "KORD", "KSFO", "KMIA"])
def test_every_fake_adsb_route_is_playable(origin: str) -> None:
    target = resolve_round_target(origin, KBOS, KBOS)

    assert target == RoundTarget("origin", origin, None)


@pytest.mark.parametrize(
    "origin, destination",
    [("KLAX", "KJFK"), (None, None), ("KJFK", None), ("", "")],
)
def test_overhead_flights_are_not_playable(origin: str | None, destination: str | None) -> None:
    target = resolve_round_target(origin, destination, KBOS)

    assert target == RoundTarget(None, None, RouteProblem.NOT_MONITORED)


@pytest.mark.parametrize(
    "origin, destination, direction",
    [("KBOS", None, "destination"), ("KBOS", "", "destination"), (None, "KBOS", "origin")],
)
def test_flights_missing_the_answer_end_are_not_playable(
    origin: str | None, destination: str | None, direction: str
) -> None:
    target = resolve_round_target(origin, destination, KBOS)

    assert target == RoundTarget(direction, None, RouteProblem.MISSING_ANSWER)


@pytest.mark.parametrize(
    "origin, destination, direction",
    [("KBOS", "KMVY", "destination"), ("KMVY", "KBOS", "origin")],
)
def test_answer_airport_missing_from_dataset_is_not_playable(
    origin: str, destination: str, direction: str
) -> None:
    target = resolve_round_target(origin, destination, KBOS)

    assert target == RoundTarget(direction, "KMVY", RouteProblem.UNKNOWN_ANSWER_AIRPORT)
    assert not target.is_playable


def test_monitored_airport_is_a_parameter() -> None:
    target = resolve_round_target("KJFK", "KLAX", "KJFK")

    assert target == RoundTarget("destination", "KLAX", None)


def test_monitored_airport_defaults_to_kbos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONITORED_AIRPORT_ICAO", raising=False)

    assert monitored_airport_icao() == "KBOS"


def test_monitored_airport_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONITORED_AIRPORT_ICAO", "KJFK")

    assert monitored_airport_icao() == "KJFK"

"""The route hint clients get instead of a plane's airports."""

import json

import pytest
from pydantic import ValidationError

from backend.schemas.plane import PlaneState, PublicPlaneState, RouteHint
from backend.services.plane_visibility import route_hint_for, to_public_plane

KBOS = "KBOS"
NO_HINT = RouteHint(guess_direction=None, known_airport=None, eligible=False)


def _ingested_plane(origin: str | None, destination: str | None) -> PlaneState:
    return PlaneState(
        hex_ident="abc123",
        lat=42.36,
        lon=-71.0,
        alt=12000,
        lat_v=0.001,
        lon_v=-0.002,
        alt_v=-300,
        last_update_ts=1700000000.0,
        trail=[(42.35, -70.99, 12100)],
        callsign="JBU123",
        operator="JetBlue",
        track=245.0,
        origin=origin,
        destination=destination,
    )


def _route_codes_in(public_plane: PublicPlaneState, *codes: str) -> list[str]:
    text = public_plane.model_dump_json()
    return [code for code in codes if code in text]


@pytest.mark.parametrize(
    "origin, destination",
    [("KBOS", "KJFK"), ("BOS", "JFK"), ("KBOS", "KBOS")],
)
def test_departure_hint_names_the_monitored_origin(origin: str, destination: str) -> None:
    hint = route_hint_for(origin, destination, KBOS)

    assert hint == RouteHint(guess_direction="destination", known_airport=KBOS, eligible=True)


@pytest.mark.parametrize("origin", ["KJFK", "JFK", "KLAX"])
def test_arrival_hint_names_the_monitored_destination(origin: str) -> None:
    hint = route_hint_for(origin, KBOS, KBOS)

    assert hint == RouteHint(guess_direction="origin", known_airport=KBOS, eligible=True)


@pytest.mark.parametrize(
    "origin, destination",
    [("KLAX", "KJFK"), ("KJFK", None), (None, "KLAX"), (None, None), ("", "")],
)
def test_overflight_hint_reveals_neither_end(origin: str | None, destination: str | None) -> None:
    assert route_hint_for(origin, destination, KBOS) == NO_HINT


@pytest.mark.parametrize(
    "origin, destination, direction",
    [
        ("KBOS", "KMVY", "destination"),
        ("KMVY", "KBOS", "origin"),
        ("KBOS", "ZZZZ", "destination"),
    ],
)
def test_answer_airport_outside_the_dataset_is_not_eligible(
    origin: str, destination: str, direction: str
) -> None:
    hint = route_hint_for(origin, destination, KBOS)

    assert hint == RouteHint(guess_direction=direction, known_airport=KBOS, eligible=False)


@pytest.mark.parametrize(
    "origin, destination, direction",
    [
        ("KBOS", None, "destination"),
        ("KBOS", "", "destination"),
        (None, "KBOS", "origin"),
        ("", "KBOS", "origin"),
    ],
)
def test_missing_answer_end_is_not_eligible(
    origin: str | None, destination: str | None, direction: str
) -> None:
    hint = route_hint_for(origin, destination, KBOS)

    assert hint == RouteHint(guess_direction=direction, known_airport=KBOS, eligible=False)


def test_known_airport_follows_the_monitored_airport() -> None:
    hint = route_hint_for("KJFK", "KLAX", "KJFK")

    assert hint == RouteHint(guess_direction="destination", known_airport="KJFK", eligible=True)


@pytest.mark.parametrize(
    "origin, destination, answer_codes",
    [("KBOS", "KJFK", ("KJFK", "JFK")), ("LAX", "KBOS", ("KLAX", "LAX"))],
)
def test_public_plane_never_carries_the_answer(
    origin: str, destination: str, answer_codes: tuple[str, ...]
) -> None:
    public_plane = to_public_plane(_ingested_plane(origin, destination), KBOS)

    assert _route_codes_in(public_plane, *answer_codes) == []


def test_public_overflight_carries_neither_end() -> None:
    public_plane = to_public_plane(_ingested_plane("KLAX", "KSFO"), KBOS)

    assert _route_codes_in(public_plane, "KLAX", "LAX", "KSFO", "SFO") == []
    assert public_plane.route_hint == NO_HINT


def test_public_plane_has_no_route_airport_fields() -> None:
    serialized = json.loads(
        to_public_plane(_ingested_plane("KBOS", "KJFK"), KBOS).model_dump_json()
    )

    assert {"origin", "destination"}.isdisjoint(serialized)


def test_public_plane_keeps_position_and_identity() -> None:
    ingested = _ingested_plane("KBOS", "KJFK")

    public_plane = to_public_plane(ingested, KBOS)

    kept = ("hex_ident", "lat", "lon", "alt", "alt_v", "trail", "callsign", "operator", "track")
    assert {field: getattr(public_plane, field) for field in kept} == {
        field: getattr(ingested, field) for field in kept
    }


def test_public_plane_refuses_route_airports() -> None:
    fields = to_public_plane(_ingested_plane("KBOS", "KJFK"), KBOS).model_dump()

    with pytest.raises(ValidationError):
        PublicPlaneState(**fields, destination="KJFK")


def test_every_public_field_is_copied_from_the_ingested_plane() -> None:
    public_fields = set(PublicPlaneState.model_fields) - {"route_hint"}

    assert public_fields - set(PlaneState.model_fields) == set()


def test_a_plane_with_only_required_ingest_fields_can_be_sent() -> None:
    ingested = PlaneState(
        hex_ident="abc123",
        lat=42.36,
        lon=-71.0,
        alt=12000,
        lat_v=0.0,
        lon_v=0.0,
        alt_v=0.0,
        last_update_ts=1700000000.0,
    )

    assert to_public_plane(ingested, KBOS).hex_ident == "abc123"

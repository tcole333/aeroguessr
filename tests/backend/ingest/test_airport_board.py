"""Local board index: parsing AeroAPI rows and matching planes by callsign."""

from datetime import datetime, timedelta, timezone

import pytest

from backend.ingest.airport_board import (
    FAKE_ORIGINS,
    AirportBoard,
    BoardDirection,
    FakeAirportBoard,
    Route,
    estimated_landing_times,
    normalize_callsign,
    parse_board_rows,
)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)


def _iso(minutes_from_now: float) -> str:
    return (NOW + timedelta(minutes=minutes_from_now)).strftime("%Y-%m-%dT%H:%M:%SZ")


def arrival_row(ident: str, origin: str, /, landing_in_min: float, **extra: object) -> dict:
    row = {
        "fa_flight_id": f"{ident}-arr",
        "ident": ident,
        "ident_icao": ident,
        "operator_icao": ident[:3],
        "origin": {"code_icao": origin},
        "destination": {"code_icao": "KBOS"},
        "scheduled_on": _iso(landing_in_min),
        "estimated_on": _iso(landing_in_min),
    }
    row.update(extra)
    return row


def departure_row(ident: str, destination: str, /, takeoff_in_min: float, **extra: object) -> dict:
    row = {
        "fa_flight_id": f"{ident}-dep",
        "ident": ident,
        "ident_icao": ident,
        "operator_icao": ident[:3],
        "origin": {"code_icao": "KBOS"},
        "destination": {"code_icao": destination},
        "scheduled_off": _iso(takeoff_in_min),
        "estimated_off": _iso(takeoff_in_min),
    }
    row.update(extra)
    return row


def _board(*, arrivals: list[dict] = (), departures: list[dict] = ()) -> AirportBoard:
    board = AirportBoard("KBOS")
    board.merge(parse_board_rows(arrivals, BoardDirection.ARRIVAL, "KBOS"))
    board.merge(parse_board_rows(departures, BoardDirection.DEPARTURE, "KBOS"))
    return board


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DAL123", "DAL123"),
        ("dal0123 ", "DAL123"),
        ("JBU 45", "JBU45"),
        ("N123AB", "N123AB"),
        ("C-GABC", "CGABC"),
        ("", None),
        (None, None),
    ],
)
def test_normalize_callsign(raw: str | None, expected: str | None) -> None:
    assert normalize_callsign(raw) == expected


def test_arriving_plane_gets_its_board_route() -> None:
    board = _board(arrivals=[arrival_row("JBU123", "KMCO", landing_in_min=20)])

    route = board.lookup("JBU123", NOW.timestamp())

    assert route == Route(origin_icao="KMCO", destination_icao="KBOS", operator="JetBlue Airways")


def test_departing_plane_gets_its_board_route() -> None:
    board = _board(departures=[departure_row("DAL456", "KATL", takeoff_in_min=-10)])

    route = board.lookup("DAL0456", NOW.timestamp())

    assert route is not None
    assert (route.origin_icao, route.destination_icao) == ("KBOS", "KATL")


def test_matches_on_atc_ident_but_not_codeshares() -> None:
    row = arrival_row("AAL4501", "KPHL", 15, atc_ident="RPA4501", codeshares=["BAW1520"])
    board = _board(arrivals=[row])

    assert board.lookup("RPA4501", NOW.timestamp()) is not None
    assert board.lookup("BAW1520", NOW.timestamp()) is None


def test_general_aviation_tail_matches_ident() -> None:
    row = arrival_row("N512AB", "KTEB", 10, ident_icao=None, operator_icao=None)
    board = _board(arrivals=[row])

    route = board.lookup("N512AB", NOW.timestamp())

    assert route is not None and route.origin_icao == "KTEB"


def test_unknown_callsign_has_no_route() -> None:
    board = _board(arrivals=[arrival_row("JBU123", "KMCO", 20)])

    assert board.lookup("XYZ999", NOW.timestamp()) is None


def test_flight_outside_its_time_window_does_not_match() -> None:
    board = _board(
        arrivals=[arrival_row("UAL1", "KORD", landing_in_min=-45)],
        departures=[departure_row("UAL2", "KORD", takeoff_in_min=45)],
    )

    assert board.lookup("UAL1", NOW.timestamp()) is None
    assert board.lookup("UAL2", NOW.timestamp()) is None


def test_same_callsign_picks_the_leg_closest_in_time() -> None:
    """A through flight lands, then leaves again under the same number."""
    board = _board(
        arrivals=[arrival_row("SWA88", "KBWI", landing_in_min=10)],
        departures=[departure_row("SWA88", "KMDW", takeoff_in_min=25)],
    )

    inbound = board.lookup("SWA88", NOW.timestamp())
    outbound = board.lookup("SWA88", (NOW + timedelta(minutes=40)).timestamp())

    assert inbound is not None and inbound.origin_icao == "KBWI"
    assert outbound is not None and outbound.destination_icao == "KMDW"


@pytest.mark.parametrize(
    "extra",
    [
        {"cancelled": True},
        {"blocked": True},
        {"position_only": True},
        {"origin": {"code_icao": None}},
        {"origin": None},
        {"destination": {"code_icao": "KPVD"}},  # diverted elsewhere
        {"scheduled_on": None, "estimated_on": None},
        {"ident": None, "ident_icao": None},
    ],
)
def test_unusable_rows_are_skipped(extra: dict) -> None:
    rows = [arrival_row("JBU123", "KMCO", 20, **extra)]

    assert parse_board_rows(rows, BoardDirection.ARRIVAL, "KBOS") == []


def test_estimated_time_falls_back_to_scheduled() -> None:
    row = arrival_row("JBU123", "KMCO", 20, estimated_on=None)

    [flight] = parse_board_rows([row], BoardDirection.ARRIVAL, "KBOS")

    assert flight.relevant_time == (NOW + timedelta(minutes=20)).timestamp()


def test_newer_row_for_the_same_flight_replaces_the_old_one() -> None:
    board = _board(arrivals=[arrival_row("JBU123", "KMCO", 20)])
    board.merge(
        parse_board_rows([arrival_row("JBU123", "KFLL", 25)], BoardDirection.ARRIVAL, "KBOS")
    )

    route = board.lookup("JBU123", NOW.timestamp())

    assert len(board) == 1
    assert route is not None and route.origin_icao == "KFLL"


def test_purge_forgets_flights_that_can_no_longer_match() -> None:
    board = _board(arrivals=[arrival_row("OLD1", "KMCO", -180), arrival_row("NEW1", "KMCO", 20)])

    board.purge(NOW.timestamp())

    assert len(board) == 1


def test_fake_board_routes_any_airline_callsign_into_the_airport() -> None:
    board = FakeAirportBoard("KBOS")

    route = board.lookup("AAL123", NOW.timestamp())

    assert route is not None
    assert route.origin_icao in FAKE_ORIGINS
    assert route.destination_icao == "KBOS"
    assert route.operator == "American Airlines"


def test_fake_board_routes_demo_planes_to_any_monitored_airport() -> None:
    board = FakeAirportBoard("KSEA")

    route = board.lookup("DAL1234", NOW.timestamp())

    assert route is not None and route.destination_icao == "KSEA"


def test_fake_board_never_routes_a_plane_from_the_monitored_airport_to_itself() -> None:
    board = FakeAirportBoard("KLAX")
    callsigns = [f"UAL{number}" for number in range(1, 200)]

    origins = {board.lookup(callsign, NOW.timestamp()).origin_icao for callsign in callsigns}

    assert origins == set(FAKE_ORIGINS) - {"KLAX"}


def test_fake_board_route_is_stable_for_a_callsign() -> None:
    board = FakeAirportBoard("KBOS")
    later = (NOW + timedelta(hours=1)).timestamp()

    assert board.lookup("UAL77", NOW.timestamp()) == board.lookup("UAL77", later)


def test_estimated_landing_times_ignore_rows_without_an_estimate() -> None:
    """A late scheduled time on an unestimated row must not count as page reach."""
    rows = [arrival_row("JBU1", "KMCO", 10), arrival_row("JBU2", "KMCO", 240, estimated_on=None)]

    assert estimated_landing_times(rows) == [(NOW + timedelta(minutes=10)).timestamp()]

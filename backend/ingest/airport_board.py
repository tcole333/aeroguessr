"""Local index of one airport's FlightAware boards, matched by callsign.

The board refresher fills this index from a few paged board requests while
someone is playing. ``handle_message`` then resolves every plane's route from
memory, so plane traffic never causes a network call.
"""

import logging
import re
import zlib
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from backend.utils.airline_codes import AIRLINE_ICAO_CODES, infer_operator_from_callsign

logger = logging.getLogger(__name__)

# A plane is matched to a board row only near that row's time: arrivals from two
# hours before landing (holding, slow approaches) to 30 minutes after (taxi-in);
# departures from 30 minutes before take-off (taxi-out) to an hour after.
ARRIVAL_MATCH_WINDOW = (-30 * 60, 120 * 60)
DEPARTURE_MATCH_WINDOW = (-60 * 60, 30 * 60)
# Rows this far in the past can no longer match anything.
PURGE_AFTER_SECONDS = 2 * 3600

FAKE_ORIGINS = ("KLAX", "KJFK", "KORD", "KSFO", "KMIA")

_AIRLINE_CALLSIGN = re.compile(r"^([A-Z]{3})0*(\d[0-9A-Z]*)$")


class BoardDirection(StrEnum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"


@dataclass(frozen=True)
class Route:
    """Where a plane is flying from and to."""

    origin_icao: str | None
    destination_icao: str | None
    operator: str | None


@dataclass(frozen=True)
class BoardFlight:
    """One usable row from an arrivals or departures board."""

    flight_id: str
    idents: frozenset[str]
    direction: BoardDirection
    route: Route
    relevant_time: float  # landing time for arrivals, take-off time for departures


class RouteLookup(Protocol):
    """Anything ``handle_message`` can resolve a callsign's route from, without I/O."""

    def lookup(self, callsign: str, now: float) -> Route | None: ...


def normalize_callsign(raw: str | None) -> str | None:
    """Uppercase, drop spaces and dashes, and strip flight-number leading zeros.

    ``"dal0123 "`` and ``"DAL123"`` both become ``"DAL123"``; a tail number such
    as ``"N123AB"`` is left as is.
    """
    if not isinstance(raw, str):
        return None
    compact = raw.upper().replace(" ", "").replace("-", "")
    if not compact:
        return None
    match = _AIRLINE_CALLSIGN.match(compact)
    return f"{match.group(1)}{match.group(2)}" if match else compact


def _parse_time(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _text(mapping: object, key: str) -> str | None:
    if not isinstance(mapping, dict):
        return None
    value = mapping.get(key)
    return value if isinstance(value, str) and value else None


def _airport_code(endpoint: object) -> str | None:
    return _text(endpoint, "code_icao")


def _first_time(row: dict, fields: tuple[str, ...]) -> float | None:
    for name in fields:
        parsed = _parse_time(row.get(name))
        if parsed is not None:
            return parsed
    return None


def estimated_landing_times(rows: Iterable[object]) -> list[float]:
    """Every row's ``estimated_on``, the time an arrivals board is ordered by.

    Rows without one are left out, rather than falling back to another time
    the way matching does, so they cannot stretch how far a page reaches.
    """
    times = (_parse_time(row.get("estimated_on")) for row in rows if isinstance(row, dict))
    return [t for t in times if t is not None]


def parse_board_rows(
    rows: Iterable[object], direction: BoardDirection, airport_icao: str
) -> list[BoardFlight]:
    """Turn AeroAPI board rows into flights, skipping anything we cannot match safely.

    Skipped: cancelled, blocked or position-only rows; rows without a far-end
    ICAO code or any usable time; rows whose near end is another airport
    (diversions); rows with no ident.
    """
    arriving = direction is BoardDirection.ARRIVAL
    near_field, far_field = ("destination", "origin") if arriving else ("origin", "destination")
    time_fields = (
        ("actual_on", "estimated_on", "scheduled_on")
        if arriving
        else ("actual_off", "estimated_off", "scheduled_off")
    )
    flights = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("cancelled") or row.get("blocked") or row.get("position_only"):
            continue
        far_icao = _airport_code(row.get(far_field))
        near_icao = _airport_code(row.get(near_field)) or airport_icao
        relevant_time = _first_time(row, time_fields)
        idents = frozenset(
            ident
            for ident in (
                normalize_callsign(_text(row, k)) for k in ("ident", "ident_icao", "atc_ident")
            )
            if ident
        )
        if not far_icao or near_icao != airport_icao or relevant_time is None or not idents:
            continue
        operator = AIRLINE_ICAO_CODES.get(_text(row, "operator_icao") or "") or (
            infer_operator_from_callsign(_text(row, "ident_icao") or _text(row, "ident"))
        )
        route = (
            Route(origin_icao=far_icao, destination_icao=airport_icao, operator=operator)
            if arriving
            else Route(origin_icao=airport_icao, destination_icao=far_icao, operator=operator)
        )
        flight_id = _text(row, "fa_flight_id") or f"{min(idents)}@{relevant_time:.0f}"
        flights.append(
            BoardFlight(
                flight_id=flight_id,
                idents=idents,
                direction=direction,
                route=route,
                relevant_time=relevant_time,
            )
        )
    return flights


class AirportBoard:
    """In-memory arrivals and departures for one airport, keyed by callsign."""

    def __init__(self, airport_icao: str) -> None:
        self.airport_icao = airport_icao
        self._flights: dict[tuple[str, BoardDirection], BoardFlight] = {}
        self._by_ident: dict[str, list[BoardFlight]] = {}

    def __len__(self) -> int:
        return len(self._flights)

    def merge(self, flights: Iterable[BoardFlight]) -> None:
        """Add or replace flights; a newer row for the same flight and direction wins."""
        for flight in flights:
            self._flights[(flight.flight_id, flight.direction)] = flight
        self._reindex()

    def purge(self, now: float) -> None:
        """Forget flights too old to match any plane."""
        cutoff = now - PURGE_AFTER_SECONDS
        stale = [key for key, f in self._flights.items() if f.relevant_time < cutoff]
        for key in stale:
            del self._flights[key]
        if stale:
            self._reindex()

    def lookup(self, callsign: str, now: float) -> Route | None:
        """Route of the board flight with this callsign closest in time to ``now``."""
        ident = normalize_callsign(callsign)
        if ident is None:
            return None
        best: BoardFlight | None = None
        for flight in self._by_ident.get(ident, ()):
            low, high = (
                ARRIVAL_MATCH_WINDOW
                if flight.direction is BoardDirection.ARRIVAL
                else DEPARTURE_MATCH_WINDOW
            )
            offset = flight.relevant_time - now
            if not low <= offset <= high:
                continue
            if best is None or abs(offset) < abs(best.relevant_time - now):
                best = flight
        return best.route if best else None

    def _reindex(self) -> None:
        self._by_ident = {}
        for flight in self._flights.values():
            for ident in flight.idents:
                self._by_ident.setdefault(ident, []).append(flight)


class FakeAirportBoard:
    """Demo-mode routes: every airline callsign flies in from a fixed set of airports.

    The origin is a stable function of the callsign, so a plane keeps its route
    for its whole flight. Makes no network calls.
    """

    def __init__(self, airport_icao: str) -> None:
        self.airport_icao = airport_icao
        self._origins = tuple(code for code in FAKE_ORIGINS if code != airport_icao)

    def lookup(self, callsign: str, now: float) -> Route | None:
        ident = normalize_callsign(callsign)
        if ident is None:
            return None
        origin = self._origins[zlib.crc32(ident.encode()) % len(self._origins)]
        return Route(
            origin_icao=origin,
            destination_icao=self.airport_icao,
            operator=infer_operator_from_callsign(ident),
        )

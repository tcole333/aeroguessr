"""Airport lookup backed by the committed dataset at ``data/airports.json``.

The same file feeds the frontend autocomplete, so every airport a player can
pick is one the backend can score. Each airport is indexed by both its IATA
and its ICAO code; two codes refer to the same airport exactly when they
resolve to the same record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Tuple

DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "airports.json"

Coords = Tuple[float, float]


@dataclass(frozen=True)
class Airport:
    """One airport record from the dataset."""

    icao: str
    iata: str | None
    name: str
    municipality: str
    country: str
    lat: float
    lon: float

    @property
    def coords(self) -> Coords:
        """Return ``(lat, lon)``."""
        return (self.lat, self.lon)


def normalize_code(code: str) -> str:
    """Return ``code`` trimmed and uppercased, the form the index is keyed by."""
    return code.strip().upper()


@lru_cache(maxsize=None)
def _load_index(path: Path) -> Mapping[str, Airport]:
    with path.open(encoding="utf-8") as fh:
        records = json.load(fh)

    index: dict[str, Airport] = {}
    for record in records:
        airport = Airport(
            icao=normalize_code(record["icao"]),
            iata=normalize_code(record["iata"]) if record.get("iata") else None,
            name=record.get("name") or "",
            municipality=record.get("municipality") or "",
            country=record.get("country") or "",
            lat=float(record["lat"]),
            lon=float(record["lon"]),
        )
        for code in (airport.icao, airport.iata):
            if code is None:
                continue
            existing = index.get(code)
            if existing is not None and existing != airport:
                raise ValueError(
                    f"Airport code '{code}' in {path} maps to both "
                    f"{existing.icao} and {airport.icao}"
                )
            index[code] = airport
    return MappingProxyType(index)


def load_airports(path: Path | None = None) -> Mapping[str, Airport]:
    """Return the airport index keyed by IATA and ICAO code.

    Reads :data:`DATA_PATH` (looked up at call time) unless ``path`` is given.

    Raises:
        FileNotFoundError: The dataset file is missing.
        ValueError: One code maps to two different airports.
    """
    return _load_index(path or DATA_PATH)


def resolve_airport(code: str | None) -> Airport | None:
    """Return the airport for an IATA or ICAO code, ignoring case and spaces."""
    if not code:
        return None
    return load_airports().get(normalize_code(code))


def same_airport(code_a: str | None, code_b: str | None) -> bool:
    """Return True when two codes name the same airport.

    Codes in the dataset compare by airport, so ``BOS`` equals ``KBOS``; codes
    missing from it only match themselves (ignoring case and spaces).
    """
    if not code_a or not code_b:
        return False
    airport_a = resolve_airport(code_a)
    airport_b = resolve_airport(code_b)
    if airport_a is not None and airport_b is not None:
        return airport_a.icao == airport_b.icao
    return normalize_code(code_a) == normalize_code(code_b)

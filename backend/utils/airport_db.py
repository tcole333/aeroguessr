"""Airport coordinates lookup util.

Loads a minimal JSON dataset (IATA/ICAO ➔ lat/lon) once and provides fast lookup
for scoring and autocomplete.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Tuple

DATA_PATH = Path(__file__).resolve().parents[2] / "sample_data" / "airports_min.json"

# Minimal built-in dataset used if the JSON file is missing. This keeps tests
# self-contained while still allowing a larger dataset to be supplied at
# runtime via ``sample_data/airports_min.json``.
# Includes both IATA and ICAO codes for common airports.
_FALLBACK_DATA: dict[str, Coords] = {
    # IATA codes
    "BOS": (42.3656, -71.0096),  # Boston Logan
    "JFK": (40.6413, -73.7781),  # JFK New York
    "PVD": (41.7234, -71.4381),  # Providence
    "FAR": (46.9207, -96.8163),  # Fargo
    "LAX": (33.9425, -118.4081),  # Los Angeles
    # ICAO codes (same coordinates as IATA)
    "KBOS": (42.3656, -71.0096),  # Boston Logan
    "KJFK": (40.6413, -73.7781),  # JFK New York
    "KPVD": (41.7234, -71.4381),  # Providence
    "KFAR": (46.9207, -96.8163),  # Fargo
    "KLAX": (33.9425, -118.4081),  # Los Angeles
}

Coords = Tuple[float, float]


@lru_cache(maxsize=1)
def _load() -> dict[str, Coords]:
    """Load airport coordinate mapping with a small built-in fallback."""
    if not DATA_PATH.exists():
        return _FALLBACK_DATA
    with DATA_PATH.open() as fh:
        raw = json.load(fh)
    mapping: dict[str, Coords] = {}
    for rec in raw:
        lat, lon = rec["lat"], rec["lon"]
        for code_key in ("iata", "icao"):
            code = rec.get(code_key)
            if code:
                mapping[code.upper()] = (lat, lon)
    return mapping


def get_coords(code: str) -> Coords | None:
    """Return (lat, lon) for IATA/ICAO code or None."""
    return _load().get(code.upper())

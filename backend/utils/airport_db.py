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

Coords = Tuple[float, float]


@lru_cache(maxsize=1)
def _load() -> dict[str, Coords]:
    # Fallback to empty dict if file missing – tests will supply small sample
    if not DATA_PATH.exists():
        return {}
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

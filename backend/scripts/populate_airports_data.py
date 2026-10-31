#!/usr/bin/env python3
"""Regenerate data/airports.json, the airport dataset shared by scoring and autocomplete.

Usage:
    uv run python backend/scripts/populate_airports_data.py

Downloads the OurAirports CSV and keeps large airports, plus medium airports
with scheduled service, that have an IATA code and coordinates. Review the diff
before committing: the backend refuses to start if the file is missing or if a
code maps to two airports, and only airports in this file can be played.
"""

import csv
import json
import logging
import urllib.request
from pathlib import Path
from typing import Iterable, Mapping

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "airports.json"


def _is_included(row: Mapping[str, str]) -> bool:
    if not (row.get("latitude_deg") and row.get("longitude_deg")):
        return False
    if not row.get("iata_code"):
        return False
    airport_type = row.get("type")
    has_scheduled_service = row.get("scheduled_service") == "yes"
    return airport_type == "large_airport" or (
        airport_type == "medium_airport" and has_scheduled_service
    )


def build_airport_records(rows: Iterable[Mapping[str, str]]) -> list[dict]:
    """Return dataset records for the OurAirports CSV ``rows``, sorted by IATA code.

    Raises:
        ValueError: A code (IATA or ICAO) would map to two different airports.
    """
    records = [
        {
            "iata": row["iata_code"],
            "icao": row.get("ident") or None,
            "name": row.get("name", ""),
            "municipality": row.get("municipality", ""),
            "country": row.get("iso_country", ""),
            "lat": float(row["latitude_deg"]),
            "lon": float(row["longitude_deg"]),
        }
        for row in rows
        if _is_included(row)
    ]

    owners: dict[str, str] = {}
    for record in records:
        for code in {record["iata"], record["icao"]} - {None}:
            owner = owners.setdefault(code, record["icao"])
            if owner != record["icao"]:
                raise ValueError(f"Airport code '{code}' maps to both {owner} and {record['icao']}")

    return sorted(records, key=lambda record: record["iata"])


def write_dataset(records: list[dict], path: Path) -> None:
    """Write ``records`` as pretty JSON with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2) + "\n")


def main(output_path: Path = DEFAULT_PATH) -> None:
    logger.info(f"Downloading airport database from {URL}")
    with urllib.request.urlopen(URL) as resp:  # noqa: S310 (URL is a constant https address)
        rows = list(csv.DictReader(resp.read().decode("utf-8").splitlines()))

    records = build_airport_records(rows)
    write_dataset(records, output_path)
    logger.info(f"Wrote {len(records):,} airports to {output_path}")


if __name__ == "__main__":
    main()

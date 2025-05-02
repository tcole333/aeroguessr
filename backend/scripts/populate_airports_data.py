#!/usr/bin/env python3
"""
fetch_airports_min.py  –  build the lookup file used by airport_coords.py

Usage:
    python fetch_airports_min.py          # writes sample_data/airports_min.json
"""

import csv
import json
import logging
import sys
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    out_dir = repo_root / "sample_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "airports_min.json"

    logger.info(f"📥  Downloading airport database from {URL}")
    with urllib.request.urlopen(URL) as resp:
        # Decode bytes to string and split into lines
        csv_data = resp.read().decode("utf-8").splitlines()
        reader = csv.DictReader(csv_data)

        logger.info("🔄  Transforming to minimal schema …")
        trimmed = [
            {
                "iata": row.get("iata_code") or None,
                "icao": row.get("ident"),
                "lat": float(row["latitude_deg"]) if row.get("latitude_deg") else None,
                "lon": float(row["longitude_deg"]) if row.get("longitude_deg") else None,
            }
            for row in reader
            if row.get("latitude_deg") and row.get("longitude_deg")
        ]

    out_file.write_text(json.dumps(trimmed, indent=2))
    logger.info(f"✅  Wrote {len(trimmed):,} records ➜ {out_file.relative_to(repo_root)}")


if __name__ == "__main__":
    sys.exit(main())

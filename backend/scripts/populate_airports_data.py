#!/usr/bin/env python3
"""
populate_airports_data.py  –  build airport lookup files for backend and frontend

Usage:
    python populate_airports_data.py    # writes sample_data/airports_min.json (backend)
                                       # and frontend/src/assets/airports.json (frontend)
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

    # Backend output directory
    backend_out_dir = repo_root / "sample_data"
    backend_out_dir.mkdir(parents=True, exist_ok=True)
    backend_out_file = backend_out_dir / "airports_min.json"

    # Frontend output directory
    frontend_out_dir = repo_root / "frontend" / "src" / "assets"
    frontend_out_dir.mkdir(parents=True, exist_ok=True)
    frontend_out_file = frontend_out_dir / "airports.json"

    logger.info(f"📥  Downloading airport database from {URL}")
    with urllib.request.urlopen(URL) as resp:
        # Decode bytes to string and split into lines
        csv_data = resp.read().decode("utf-8").splitlines()
        reader = csv.DictReader(csv_data)

        # Convert to list to process twice
        rows = list(reader)

        # 1. Backend dataset - minimal schema, all airports with coordinates
        logger.info("🔄  Creating backend dataset (all airports)...")
        backend_data = [
            {
                "iata": row.get("iata_code") or None,
                "icao": row.get("ident"),
                "lat": float(row["latitude_deg"]) if row.get("latitude_deg") else None,
                "lon": float(row["longitude_deg"]) if row.get("longitude_deg") else None,
            }
            for row in rows
            if row.get("latitude_deg") and row.get("longitude_deg")
        ]

        # 2. Frontend dataset - filtered, enriched schema
        logger.info("🔄  Creating frontend dataset (major airports only)...")
        frontend_data = []
        for row in rows:
            # Skip if no coordinates
            if not (row.get("latitude_deg") and row.get("longitude_deg")):
                continue

            # More restrictive filtering:
            # 1. Must have scheduled service AND be large/medium airport
            # 2. OR be a large airport (even without scheduled service)
            has_scheduled_service = row.get("scheduled_service") == "yes"
            is_large_airport = row.get("type") == "large_airport"
            is_medium_airport = row.get("type") == "medium_airport"

            if not (
                (has_scheduled_service and (is_large_airport or is_medium_airport))
                or is_large_airport
            ):
                continue

            # Skip heliports, seaplane bases, and closed airports
            if row.get("type") in ["heliport", "seaplane_base", "closed"]:
                continue

            # Must have IATA code (more restrictive - only airports with IATA codes)
            iata_code = row.get("iata_code") or None
            if not iata_code:
                continue

            icao_code = row.get("ident") or None

            frontend_data.append(
                {
                    "iata": iata_code,
                    "icao": icao_code,
                    "name": row.get("name", ""),
                    "municipality": row.get("municipality", ""),
                    "country": row.get("iso_country", ""),
                    "lat": float(row["latitude_deg"]),
                    "lon": float(row["longitude_deg"]),
                }
            )

        # Sort frontend data by IATA code (prioritizing airports with IATA codes)
        frontend_data.sort(key=lambda x: (x["iata"] is None, x["iata"] or x["icao"] or ""))

    # Write backend file
    backend_out_file.write_text(json.dumps(backend_data, indent=2))
    logger.info(
        f"✅  Backend: {len(backend_data):,} records ➜ {backend_out_file.relative_to(repo_root)}"
    )

    # Write frontend file
    frontend_out_file.write_text(json.dumps(frontend_data, indent=2))
    logger.info(
        f"✅  Frontend: {len(frontend_data):,} records ➜ {frontend_out_file.relative_to(repo_root)}"
    )

    # Check file sizes
    backend_size = backend_out_file.stat().st_size / 1024 / 1024
    frontend_size = frontend_out_file.stat().st_size / 1024 / 1024
    logger.info(f"📊  Backend file size: {backend_size:.1f} MB")
    logger.info(f"📊  Frontend file size: {frontend_size:.1f} MB")

    # Estimate gzipped size (roughly 20-25% of JSON size)
    frontend_gzip_estimate = frontend_size * 0.22 * 1024  # Convert to KB
    logger.info(f"📊  Frontend gzipped estimate: ~{frontend_gzip_estimate:.0f} KB")


if __name__ == "__main__":
    sys.exit(main())

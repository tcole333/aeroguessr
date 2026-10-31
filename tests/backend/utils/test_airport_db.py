"""Behaviour of the airport lookup against the committed dataset."""

import json
from pathlib import Path

import pytest

from backend.utils import airport_db

# Answers the FAKE_ADSB demo produces (backend/ingest/enrichment*.py) plus the
# monitored airport; every one of them must be scorable.
DEMO_AIRPORTS = ["KLAX", "KJFK", "KORD", "KSFO", "KMIA", "KBOS"]


def _write_dataset(path: Path, records: list[dict]) -> Path:
    path.write_text(json.dumps(records))
    return path


def _record(iata: str, icao: str) -> dict:
    return {
        "iata": iata,
        "icao": icao,
        "name": f"{icao} Airport",
        "municipality": "Somewhere",
        "country": "US",
        "lat": 40.0,
        "lon": -70.0,
    }


def test_iata_and_icao_resolve_to_same_airport() -> None:
    assert airport_db.resolve_airport("ORD") == airport_db.resolve_airport("KORD")


def test_resolved_airport_carries_both_codes() -> None:
    airport = airport_db.resolve_airport("ORD")

    assert airport is not None
    assert (airport.icao, airport.iata) == ("KORD", "ORD")


def test_resolution_ignores_case_and_whitespace() -> None:
    airport = airport_db.resolve_airport(" kord ")

    assert airport is not None
    assert airport.icao == "KORD"


@pytest.mark.parametrize("code", ["ZZZZ", "", None, "KMVY"])
def test_unknown_or_empty_code_resolves_to_none(code: str | None) -> None:
    assert airport_db.resolve_airport(code) is None


@pytest.mark.parametrize("code", DEMO_AIRPORTS)
def test_dataset_covers_demo_airports(code: str) -> None:
    assert airport_db.resolve_airport(code) is not None


def test_dataset_codes_fit_guess_length_limits() -> None:
    codes = airport_db.load_airports().keys()

    assert all(3 <= len(code) <= 8 for code in codes)


def test_dataset_coordinates_are_valid() -> None:
    airports = airport_db.load_airports().values()

    assert all(-90 <= a.lat <= 90 and -180 <= a.lon <= 180 for a in airports)


def test_missing_dataset_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        airport_db.load_airports(tmp_path / "missing.json")


def test_code_shared_by_two_airports_raises(tmp_path: Path) -> None:
    path = _write_dataset(
        tmp_path / "airports.json",
        [_record("ABC", "KABC"), _record("XYZ", "ABC")],
    )

    with pytest.raises(ValueError, match="'ABC'"):
        airport_db.load_airports(path)


def test_airport_whose_iata_equals_its_icao_loads(tmp_path: Path) -> None:
    path = _write_dataset(tmp_path / "airports.json", [_record("AXF", "AXF")])

    assert airport_db.load_airports(path)["AXF"].icao == "AXF"


def test_loader_reads_data_path_at_call_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write_dataset(tmp_path / "airports.json", [_record("ABC", "KABC")])
    monkeypatch.setattr(airport_db, "DATA_PATH", path)

    assert set(airport_db.load_airports()) == {"ABC", "KABC"}


@pytest.mark.parametrize(
    "code_a, code_b, expected",
    [
        ("BOS", "KBOS", True),
        ("kbos", " KBOS", True),
        ("BOS", "JFK", False),
        ("KMVY", "kmvy", True),  # not in the dataset: compared as codes
        ("KMVY", "KBOS", False),
        (None, None, False),
        ("", "", False),
    ],
)
def test_same_airport(code_a: str | None, code_b: str | None, expected: bool) -> None:
    assert airport_db.same_airport(code_a, code_b) is expected

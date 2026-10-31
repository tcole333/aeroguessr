"""Building the airport dataset from OurAirports CSV rows."""

import csv
import json
from pathlib import Path

import pytest

from backend.scripts.populate_airports_data import build_airport_records, write_dataset

CSV_HEADER = (
    "id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,"
    "iso_country,iso_region,municipality,scheduled_service,icao_code,iata_code,"
    "gps_code,local_code,home_link,wikipedia_link,keywords"
)

SAMPLE_CSV_DATA = "\n".join(
    [
        CSV_HEADER,
        "1,KATL,large_airport,Hartsfield Jackson Atlanta International Airport,"
        "33.6367,-84.428101,1026,NA,US,US-GA,Atlanta,yes,KATL,ATL,KATL,ATL,,,",
        "2,KBOS,large_airport,Logan International Airport,42.36197,-71.0079,19,"
        "NA,US,US-MA,Boston,yes,KBOS,BOS,KBOS,BOS,,,",
        "3,KJFK,large_airport,John F Kennedy International Airport,40.63974,"
        "-73.77853,13,NA,US,US-NY,New York,yes,KJFK,JFK,KJFK,JFK,,,",
        "4,SMALL,small_airport,Small Regional Airport,41.123,-72.456,100,"
        "NA,US,US-CT,Hartford,yes,KSMALL,SML,KSMALL,SML,,,",
        "5,MEDIUM,medium_airport,Medium City Airport,42.789,-73.123,200,"
        "NA,US,US-VT,Burlington,yes,KMED,MED,KMED,MED,,,",
        "6,NOIA,medium_airport,No IATA Airport,43.456,-74.789,300,"
        "NA,US,US-NH,Manchester,yes,KNOIA,,KNOIA,NOIA,,,",
        "7,NOSCHED,large_airport,No Schedule Airport,44.123,-75.456,400,"
        "NA,US,US-ME,Portland,no,KNOSCH,NSC,KNOSCH,NSC,,,",
        "8,HELI,heliport,City Heliport,40.123,-73.456,50,"
        "NA,US,US-NY,New York,yes,KHELI,HLP,KHELI,HLP,,,",
        "9,CLOSED,closed,Closed Airport,39.123,-72.456,100,"
        "NA,US,US-NJ,Newark,no,KCLOSED,CLS,KCLOSED,CLS,,,",
        "10,NOLOC,large_airport,No Location Airport,,,500,"
        "NA,US,US-CA,Los Angeles,yes,KNOLOC,NLC,KNOLOC,NLC,,,",
        "11,KMED2,medium_airport,Medium no Schedule,43.0,-73.0,100,"
        "NA,US,US-NY,New York,no,KMED2,MD2,,,,,",
    ]
)


def _rows(csv_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(csv_text.splitlines()))


def test_keeps_large_airports_and_scheduled_medium_airports_with_iata_codes() -> None:
    records = build_airport_records(_rows(SAMPLE_CSV_DATA))

    assert [r["iata"] for r in records] == ["ATL", "BOS", "JFK", "MED", "NSC"]


def test_records_use_the_dataset_schema() -> None:
    records = build_airport_records(_rows(SAMPLE_CSV_DATA))

    assert records[1] == {
        "iata": "BOS",
        "icao": "KBOS",
        "name": "Logan International Airport",
        "municipality": "Boston",
        "country": "US",
        "lat": 42.36197,
        "lon": -71.0079,
    }


def test_a_code_shared_by_two_airports_is_rejected() -> None:
    duplicate_iata = "\n".join(
        [
            CSV_HEADER,
            "1,KAAA,large_airport,First,40.0,-70.0,1,NA,US,US-NY,A,yes,KAAA,AAA,,,,,",
            "2,KBBB,large_airport,Second,41.0,-71.0,1,NA,US,US-NY,B,yes,KBBB,AAA,,,,,",
        ]
    )

    with pytest.raises(ValueError, match="'AAA'"):
        build_airport_records(_rows(duplicate_iata))


def test_written_dataset_is_pretty_json_with_trailing_newline(tmp_path: Path) -> None:
    records = build_airport_records(_rows(SAMPLE_CSV_DATA))
    path = tmp_path / "data" / "airports.json"

    write_dataset(records, path)

    assert path.read_text() == json.dumps(records, indent=2) + "\n"


def test_committed_dataset_is_in_the_written_format() -> None:
    committed = Path(__file__).resolve().parents[3] / "data" / "airports.json"
    text = committed.read_text()
    records = json.loads(text)

    assert text == json.dumps(records, indent=2) + "\n"
    assert records == sorted(records, key=lambda r: r["iata"])

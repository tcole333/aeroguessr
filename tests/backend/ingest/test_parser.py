import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from backend.ingest.parser import RawMessage, parse_sbs_message

# Define the path to the fixture file relative to the project root
# Assumes tests are run from the project root directory
FIXTURE_PATH = Path("sample_data/sbs_parser_fixtures.sbs")


@pytest.fixture(scope="module")
def sbs_fixture_lines() -> List[str]:
    """Reads the SBS fixture file and returns a list of lines."""
    if not FIXTURE_PATH.is_file():
        pytest.fail(f"Fixture file not found at: {FIXTURE_PATH.resolve()}")
    with open(FIXTURE_PATH, "r") as f:
        # Read lines, strip whitespace, ignore comments and empty lines
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


# Get the current timestamp once for all tests in this module
CURRENT_TIMESTAMP = time.time()


# --- Test Cases using Parametrization ---


@pytest.mark.parametrize(
    "line_index, expected_fields",  # Renamed expected_data to expected_fields for clarity
    [
        (
            5,  # MSG,1: ES Identification and Category
            {
                "msg_type": 1,
                "hex_ident": "7404F2",
                "callsign": "RJA1118",
                "altitude": None,
                "latitude": None,
                "longitude": None,
                "ground_speed": None,
                "track": None,
                "vertical_rate": None,
                "squawk": None,
            },
        ),
        (
            6,  # MSG,2: ES Surface Position Message
            {
                "msg_type": 2,
                "hex_ident": "400CB6",
                "callsign": None,
                "altitude": None,  # Field 11 is empty in fixture
                "latitude": 54.05735,  # Field 15
                "longitude": -4.38826,  # Field 16
                "ground_speed": 0.0,  # Field 12 is '0'
                "track": 76.4,  # Field 13 is '76.4'
                "vertical_rate": None,
                "squawk": None,
            },
        ),
        (
            7,  # MSG,3: ES Airborne Position Message
            {
                "msg_type": 3,
                "hex_ident": "4CA2D6",
                "callsign": None,
                "altitude": 37000,
                "latitude": 51.45735,
                "longitude": -1.02826,
                "ground_speed": None,
                "track": None,
                "vertical_rate": None,
                "squawk": None,
            },
        ),
        (
            8,  # MSG,4: ES Airborne Velocity Message
            {
                "msg_type": 4,
                "hex_ident": "4CA767",
                "callsign": None,
                "altitude": None,  # Altitude not part of MSG,4 standard fields
                "latitude": None,
                "longitude": None,
                "ground_speed": 288.6,
                "track": 103.2,
                "vertical_rate": -832,
                "squawk": None,
            },
        ),
        (
            9,  # MSG,5: Surveillance Altitude Message
            {
                "msg_type": 5,
                "hex_ident": "394A65",
                "callsign": None,
                "altitude": 10000,  # Primary info is altitude
                "latitude": None,
                "longitude": None,
                "ground_speed": None,
                "track": None,
                "vertical_rate": None,
                "squawk": None,  # Squawk might appear here but isn't the primary source
            },
        ),
        # Fixture data does not contain MSG,6, MSG,7, or MSG,8 examples.
        # If added, tests should be updated accordingly.
        # Example expectation for a hypothetical MSG,6:
        # {
        #     "msg_type": 6, "hex_ident": "SOMEHEX", "callsign": None,
        #     "altitude": None, # Altitude might appear but isn't primary source
        #     "latitude": None, "longitude": None, "ground_speed": None, "track": None,
        #     "vertical_rate": None, "squawk": "1234"
        # }
        # Example expectation for a hypothetical MSG,7:
        # {
        #     "msg_type": 7, "hex_ident": "SOMEHEX", "callsign": None,
        #     "altitude": 25000, # Primary info is altitude
        #     "latitude": None, "longitude": None, "ground_speed": None, "track": None,
        #     "vertical_rate": None, "squawk": None
        # }
        # MSG,8 has no standard position/velocity fields parsed by this implementation.
    ],
)
def test_parse_valid_msg_messages(
    sbs_fixture_lines: List[str], line_index: int, expected_fields: Dict[str, Any]
) -> None:
    """Tests parsing various valid MSG message types from the fixture file."""
    sbs_line = sbs_fixture_lines[line_index]
    actual = parse_sbs_message(sbs_line, CURRENT_TIMESTAMP)

    assert actual is not None
    assert isinstance(actual, RawMessage)
    assert actual.timestamp == CURRENT_TIMESTAMP
    assert actual.raw_sbs == sbs_line

    # Compare expected fields dynamically
    for field, expected_value in expected_fields.items():
        actual_value = getattr(actual, field)
        # Use pytest.approx for float comparisons
        if isinstance(expected_value, float):
            # Check for None explicitly before comparing floats
            assert (
                actual_value is not None
            ), f"Field '{field}' expected {expected_value} but got None"
            assert actual_value == pytest.approx(expected_value), f"Field '{field}' mismatch"
        else:
            assert actual_value == expected_value, f"Field '{field}' mismatch"

    # Ensure fields *not* expected for this message type are None
    all_data_fields = {
        "callsign",
        "altitude",
        "latitude",
        "longitude",
        "ground_speed",
        "track",
        "vertical_rate",
        "squawk",
    }
    expected_none_fields = all_data_fields - set(expected_fields.keys())
    for field in expected_none_fields:
        assert (
            getattr(actual, field) is None
        ), f"Field '{field}' should be None but is {getattr(actual, field)}"


@pytest.mark.parametrize(
    "line_index",
    [
        0,  # SEL line
        1,  # ID line
        2,  # AIR line
        3,  # STA line
        4,  # CLK line
    ],
)
def test_parse_non_msg_lines(sbs_fixture_lines: List[str], line_index: int) -> None:
    """Tests that non-MSG lines correctly return None."""
    sbs_line = sbs_fixture_lines[line_index]
    actual = parse_sbs_message(sbs_line, CURRENT_TIMESTAMP)
    assert actual is None


# --- Edge Case Tests ---


def test_parse_empty_line() -> None:
    """Tests parsing an empty string."""
    actual = parse_sbs_message("", CURRENT_TIMESTAMP)
    assert actual is None


def test_parse_whitespace_line() -> None:
    """Tests parsing a string with only whitespace."""
    actual = parse_sbs_message("   \t\n ", CURRENT_TIMESTAMP)
    assert actual is None


def test_parse_non_sbs_line() -> None:
    """Tests parsing a line that doesn't conform to SBS format."""
    actual = parse_sbs_message("This is not an SBS message", CURRENT_TIMESTAMP)
    assert actual is None


def test_parse_msg_invalid_type() -> None:
    """Tests parsing an MSG line with an invalid transmission type."""
    invalid_line = (
        "MSG,9,1,1,A8C1FE,1,2025/04/27,10:00:05.456,2025/04/27,10:00:05.456,"
        ",35000,,,42.365,-71.010,,,,,,"
    )
    actual = parse_sbs_message(invalid_line, CURRENT_TIMESTAMP)
    assert actual is None  # Type 9 is invalid

    invalid_line_str = (
        "MSG,XYZ,1,1,A8C1FE,1,2025/04/27,10:00:05.456,2025/04/27,10:00:05.456,"
        ",35000,,,42.365,-71.010,,,,,,"
    )
    actual = parse_sbs_message(invalid_line_str, CURRENT_TIMESTAMP)
    assert actual is None  # Type XYZ is invalid


def test_parse_msg_missing_hex_ident() -> None:
    """Tests parsing an MSG line with a missing hex_ident (field 4)."""
    invalid_line = (
        "MSG,3,1,1,,1,2025/04/27,10:00:05.456,2025/04/27,10:00:05.456,,35000,,,42.365,-71.010,,,,,,"
    )
    actual = parse_sbs_message(invalid_line, CURRENT_TIMESTAMP)
    assert actual is None


def test_parse_msg_too_short() -> None:
    """Tests parsing an MSG line that is too short."""
    short_line = "MSG,1,1,1,ABCDEF"  # Only 5 fields, less than minimum 11
    actual = parse_sbs_message(short_line, CURRENT_TIMESTAMP)
    assert actual is None


def test_parse_msg_corrupt_numeric() -> None:
    """Tests parsing an MSG line with non-numeric data in expected numeric fields."""
    # MSG,3 expects altitude (11), lat (14), lon (15) to be numeric
    corrupt_alt = (
        "MSG,3,1,1,A8C1FE,1,2025/04/27,10:00:05.456,2025/04/27,10:00:05.456,"
        ",NOT_AN_ALT,,,42.365,-71.010,,,,,,"
    )
    actual_alt = parse_sbs_message(corrupt_alt, CURRENT_TIMESTAMP)
    # Parser should still succeed but altitude will be None
    assert actual_alt is not None
    assert actual_alt.altitude is None
    assert actual_alt.latitude == pytest.approx(42.365)  # Other fields might parse ok
    assert actual_alt.longitude == pytest.approx(-71.010)

    corrupt_lat = (
        "MSG,3,1,1,A8C1FE,1,2025/04/27,10:00:05.456,2025/04/27,10:00:05.456,"
        ",35000,,,BAD_LAT,-71.010,,,,,,"
    )
    actual_lat = parse_sbs_message(corrupt_lat, CURRENT_TIMESTAMP)
    assert actual_lat is not None
    assert actual_lat.altitude == 35000
    assert actual_lat.latitude is None
    assert actual_lat.longitude == pytest.approx(-71.010)


def test_parse_msg_index_error() -> None:
    """Tests parsing an MSG line that claims a type but lacks required fields."""
    # MSG,1 requires callsign at index 10. This line only has 10 fields (0-9).
    short_msg1 = "MSG,1,145,256,7404F2,11267,2008/11/28,23:48:18.611,2008/11/28,23:53:19.161"
    actual = parse_sbs_message(short_msg1, CURRENT_TIMESTAMP)
    # The parser now handles IndexError internally and logs a warning
    assert actual is None


# Consider adding tests for MSG,6 squawk parsing if sample data becomes available.
# Example:
# def test_parse_msg6_squawk():
#    line = "MSG,6,1,1,A1B2C3,1,2025/01/01,12:00:00.000,2025/01/01,12:00:00.000,,,,,,,,1234,,,,"
#    msg = parse_sbs_message(line, time.time())
#    assert msg is not None
#    assert msg.msg_type == 6
#    assert msg.hex_ident == "A1B2C3"
#    assert msg.squawk == "1234"
#    assert msg.altitude is None # Assuming altitude wasn't present or primary

# To run these tests:
# 1. Navigate to the root project directory (`plane-game-v4`)
# 2. Ensure poetry dependencies are installed: `poetry install`
# 3. Execute from root: `poetry run pytest tests/backend/ingest/test_parser.py`

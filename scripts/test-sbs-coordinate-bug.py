#!/usr/bin/env python3
# ruff: noqa: T201, E501
"""Test script to verify SBS parser coordinate bug and propose fix."""

import sys

sys.path.append(".")

import time

from backend.ingest.parser import parse_sbs_message

# Test cases with known coordinate values
test_cases = [
    # MSG,2 from fixture - appears to have malformed data
    {
        "line": "MSG,2,496,603,400CB6,13168,2008/10/13,12:24:32.414,2008/10/13,12:28:52.074,,,0,76.4,258.3,54.05735,-4.38826,,,,,,0",
        "expected_lat": 54.05735,  # Looks like latitude
        "expected_lon": -4.38826,  # Looks like longitude
        "msg_type": 2,
    },
    # MSG,3 from fixture - correct format
    {
        "line": "MSG,3,496,211,4CA2D6,10057,2008/11/28,14:53:50.594,2008/11/28,14:58:51.153,,37000,,,51.45735,-1.02826,,,0,0,0,0",
        "expected_lat": 51.45735,
        "expected_lon": -1.02826,
        "msg_type": 3,
    },
    # Synthetic MSG,2 with proper field layout (lat in field 14, lon in field 15)
    {
        "line": "MSG,2,1,1,A00001,1,2025/01/01,12:00:00.000,2025/01/01,12:00:00.000,,,10,90.0,42.3614,-71.0589,0,,,,,,1",
        "expected_lat": 42.3614,
        "expected_lon": -71.0589,
        "msg_type": 2,
    },
]

print("Testing SBS Parser Coordinate Handling\n")
print("=" * 80)

for i, test in enumerate(test_cases):
    print(f"\nTest Case {i + 1}: MSG,{test['msg_type']}")
    print(f"Line: {test['line'][:100]}...")

    # Parse the line
    result = parse_sbs_message(test["line"], time.time())

    if result:
        print("  Parsed successfully")
        print("  Current parser results:")
        print(f"    Latitude:  {result.latitude}")
        print(f"    Longitude: {result.longitude}")
        print("  Expected values:")
        print(f"    Latitude:  {test['expected_lat']}")
        print(f"    Longitude: {test['expected_lon']}")

        # Check if values match expectations
        lat_match = result.latitude == test["expected_lat"] if result.latitude else False
        lon_match = result.longitude == test["expected_lon"] if result.longitude else False

        if lat_match and lon_match:
            print("  ✓ Coordinates match expected values")
        else:
            print("  ✗ Coordinates DO NOT match expected values!")

            # Analyze the fields
            parts = test["line"].split(",")
            print("\n  Field analysis:")
            print(f"    Field 14: '{parts[14]}' (should be latitude per SBS-1 spec)")
            print(f"    Field 15: '{parts[15]}' (should be longitude per SBS-1 spec)")
            if len(parts) > 16:
                print(f"    Field 16: '{parts[16]}' (should be vertical rate per SBS-1 spec)")
    else:
        print("  Failed to parse!")

print("\n" + "=" * 80)
print("\nCONCLUSIONS:")
print("1. MSG,3 parsing is correct (uses fields 14 & 15 for lat/lon)")
print("2. MSG,2 parsing is INCORRECT (uses fields 15 & 16 for lat/lon)")
print(
    "3. The fixture data for MSG,2 appears malformed (field 14 contains '258.3' which is not a valid latitude)"
)
print("4. The bug causes MSG,2 coordinates to be shifted by one field")
print("\nRECOMMENDED FIX:")
print("Update parser.py lines 125-126 to use the same fields as MSG,3:")
print("  message.latitude = _parse_float(parts[14])  # was parts[15]")
print("  message.longitude = _parse_float(parts[15]) # was parts[16]")

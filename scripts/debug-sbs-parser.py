#!/usr/bin/env python3
# ruff: noqa: T201, E501
"""Debug script to analyze SBS message parsing."""

# Sample MSG,2 line from fixture
msg2_line = (
    "MSG,2,496,603,400CB6,13168,2008/10/13,12:24:32.414,"
    "2008/10/13,12:28:52.074,,,0,76.4,258.3,54.05735,-4.38826,,,,,,0"
)

# Sample MSG,3 line from fixture
msg3_line = (
    "MSG,3,496,211,4CA2D6,10057,2008/11/28,14:53:50.594,"
    "2008/11/28,14:58:51.153,,37000,,,51.45735,-1.02826,,,0,0,0,0"
)


def analyze_msg(line: str, msg_type: int) -> None:
    parts = line.split(",")
    print(f"\nAnalyzing MSG type {msg_type}:")
    print(f"Total fields: {len(parts)}")

    # Print relevant fields with indices
    for i in range(10, min(len(parts), 22)):
        print(f"  parts[{i:2d}]: '{parts[i]:15s}' ", end="")

        # Add field description based on SBS-1 spec
        if i == 10:
            print("# Callsign")
        elif i == 11:
            print("# Altitude")
        elif i == 12:
            print("# Ground Speed")
        elif i == 13:
            print("# Track")
        elif i == 14:
            print("# Latitude (MSG 2,3)")
        elif i == 15:
            print("# Longitude (MSG 2,3)")
        elif i == 16:
            print("# Vertical Rate")
        elif i == 17:
            print("# Squawk")
        elif i == 18:
            print("# Alert")
        elif i == 19:
            print("# Emergency")
        elif i == 20:
            print("# SPI")
        elif i == 21:
            print("# Is On Ground")
        else:
            print()


analyze_msg(msg2_line, 2)
analyze_msg(msg3_line, 3)

# What the parser currently does vs what it should do
print("\n\nCURRENT PARSER BEHAVIOR:")
print("MSG,2: latitude = parts[15] = '54.05735', longitude = parts[16] = '-4.38826'")
print("MSG,3: latitude = parts[14] = '51.45735', longitude = parts[15] = '-1.02826'")

print("\n\nCORRECT BEHAVIOR (per SBS-1 spec):")
print("MSG,2: latitude = parts[14] = '258.3', longitude = parts[15] = '54.05735'")
print("MSG,3: latitude = parts[14] = '51.45735', longitude = parts[15] = '-1.02826'")

print("\n\nWAIT! The value '258.3' in field 14 doesn't look like a latitude!")
print("It looks more like a heading/track value (0-360 degrees).")
print("\nLet's check if the fixture data itself might be malformed...")

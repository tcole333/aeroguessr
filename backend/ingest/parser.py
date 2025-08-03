import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_int(value: str) -> Optional[int]:
    """Safely parse a string to an integer."""
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_float(value: str) -> Optional[float]:
    """Safely parse a string to a float."""
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_str(value: str) -> Optional[str]:
    """Return the string if not empty, else None."""
    return value if value else None


@dataclass
class RawMessage:
    """Represents a decoded ADS-B message before smoothing or enrichment."""

    timestamp: float  # Epoch timestamp of message reception
    hex_ident: str  # ICAO 24-bit hex identifier
    raw_sbs: str = field(repr=False)  # Original SBS-1 message
    msg_type: Optional[int] = None  # SBS Transmission Type (1-8 for MSG)
    callsign: Optional[str] = None
    altitude: Optional[int] = None  # In feet
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ground_speed: Optional[float] = None  # In knots
    track: Optional[float] = None  # True track angle (degrees)
    vertical_rate: Optional[int] = None  # In feet/minute
    squawk: Optional[str] = None


def parse_sbs_message(sbs_line: str, timestamp: float) -> Optional[RawMessage]:
    """Parses a single SBS-1 formatted line into a RawMessage.

    Handles only 'MSG' type messages, extracting data based on the
    transmission type specified within the message. Other message types
    (SEL, ID, AIR, STA, CLK) are ignored.

    Reference for fields by Transmission Type:
    http://woodair.net/SBS/Article/Barebones42_Socket_Data.htm

    Args:
        sbs_line: The raw SBS-1 message string.
        timestamp: The reception timestamp (epoch seconds).

    Returns:
        A RawMessage object if parsing is successful (for MSG types),
        None otherwise.

    Example:
        >>> line = ("MSG,3,1,1,AC1234,1,2023/01/01,12:00:00.000,"
        ...         "2023/01/01,12:00:00.000,,35000,,,47.123,-1.456,,,,")
        >>> msg = parse_sbs_message(line, 1672574400.0)
        >>> if msg:
        ...     print(msg.hex_ident, msg.altitude, msg.latitude, msg.longitude)
        AC1234 35000 47.123 -1.456
    """
    parts = sbs_line.strip().split(",")
    if not parts or parts[0] != "MSG":
        return None  # Ignore non-MSG lines

    # Basic validation: MSG lines should have at least 11 fields
    # The longest (MSG,4) can have up to 22.
    if len(parts) < 11:
        logger.warning(f"Ignoring malformed MSG line (too short): {sbs_line}")
        return None

    hex_ident = _parse_str(parts[4])
    if not hex_ident:
        logger.warning(f"Ignoring MSG line with missing hex_ident: {sbs_line}")
        return None

    msg_type = _parse_int(parts[1])
    if msg_type is None or not (1 <= msg_type <= 8):
        logger.warning(f"Ignoring MSG line with invalid transmission type '{parts[1]}': {sbs_line}")
        return None

    message = RawMessage(
        timestamp=timestamp,
        hex_ident=hex_ident,
        raw_sbs=sbs_line,
        msg_type=msg_type,
    )

    # Field indices based on SBS-1 spec (0-based)
    # 10: Callsign      (MSG,1)
    # 11: Altitude      (MSG,2,3,5,7)
    # 12: Ground Speed  (MSG,2,4)
    # 13: Track         (MSG,2,4)
    # 14: Latitude      (MSG,2,3)
    # 15: Longitude     (MSG,2,3)
    # 16: Vertical Rate (MSG,4)
    # 17: Squawk        (MSG,6)
    # 18: Alert         (MSG,5,6) - Not stored
    # 19: Emergency     (MSG,5)   - Not stored
    # 20: SPI           (MSG,5)   - Not stored
    # 21: Is On Ground  (MSG,2,3,4,5,7) - Not stored directly, may infer later

    try:
        if msg_type == 1:  # ES Identification and Category
            message.callsign = _parse_str(parts[10])
        elif msg_type == 2:  # ES Surface Position Message
            message.altitude = _parse_int(parts[11])
            message.ground_speed = _parse_float(parts[12])
            message.track = _parse_float(parts[13])
            message.latitude = _parse_float(parts[14])  # Fixed: was parts[15]
            message.longitude = _parse_float(parts[15])  # Fixed: was parts[16]
        elif msg_type == 3:  # ES Airborne Position Message
            message.altitude = _parse_int(parts[11])
            message.latitude = _parse_float(parts[14])
            message.longitude = _parse_float(parts[15])
        elif msg_type == 4:  # ES Airborne Velocity Message
            message.ground_speed = _parse_float(parts[12])
            message.track = _parse_float(parts[13])
            message.vertical_rate = _parse_int(parts[16])
        elif msg_type == 5:  # Surveillance Alt Message (Mode-S altitude)
            message.altitude = _parse_int(parts[11])
            # Squawk code *might* be present here too in some implementations,
            # but MSG,6 is the primary source. We prioritize MSG,6 if seen.
            # parts[17] is squawk, parts[18] alert, parts[19] emergency, parts[20] SPI
        elif msg_type == 6:  # Surveillance ID Message (Mode-S squawk)
            message.squawk = _parse_str(parts[17])
            # parts[11] might contain altitude, parts[18] alert, parts[20] SPI
            # We only reliably care about squawk from type 6. Altitude from type 3/5 preferred.
            # Check if altitude is present and not already set
            if len(parts) > 11 and parts[11] and message.altitude is None:
                message.altitude = _parse_int(parts[11])
        elif msg_type == 7:  # Air To Air Message
            message.altitude = _parse_int(parts[11])
        elif msg_type == 8:  # All Call Reply (Mode-S Comm-B)
            # Contains ICAO, Flight Status, Downlink Request, Utility Message, Comm-B data segment
            # No standard position/velocity fields defined in SBS format here.
            pass  # Typically less useful for basic tracking

    except IndexError:
        # This might happen if a message claims a type but lacks expected fields.
        logger.warning(f"Ignoring MSG {msg_type} line with insufficient fields: {sbs_line}")
        return None
    except (ValueError, TypeError) as e:
        # Should be caught by helper funcs, but as a safeguard.
        logger.error(f"Parsing error for MSG {msg_type} line: {sbs_line} - Error: {e}")
        return None

    return message

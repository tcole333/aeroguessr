"""Planes as the ingest stores them, and what clients may know about them.

One end of every playable route is a round's answer, so the server never tells
clients a route's airports before ``roundResult``. It sends a ``RouteHint``
instead: which end would be guessed, the monitored end that is already public,
and whether the plane can be played at all.
"""

import time
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

GuessDirection = Literal["origin", "destination"]


class PlaneState(BaseModel):
    """Represents the smoothed state of an aircraft stored in Redis.

    Includes core position/velocity, a capped trail, and the resolved route.
    """

    hex_ident: str = Field(..., description="Aircraft ICAO hex identifier.")
    lat: float = Field(..., description="Smoothed latitude.")
    lon: float = Field(..., description="Smoothed longitude.")
    alt: float = Field(..., description="Smoothed altitude in feet.")
    lat_v: float = Field(..., description="Smoothed latitude velocity.")
    lon_v: float = Field(..., description="Smoothed longitude velocity.")
    alt_v: float = Field(
        ..., description="Smoothed vertical rate in feet per minute, positive when climbing."
    )
    last_update_ts: float = Field(..., description="Timestamp of the last update.")
    trail: List[Tuple[float, float, float]] = Field(
        default_factory=list,
        description="List of recent (lat, lon, alt) tuples, capped at 10.",
    )
    callsign: Optional[str] = Field(None, description="Aircraft callsign (cached).")
    # Raw ADS-B track (heading from aircraft broadcast)
    track: Optional[float] = Field(
        None, description="Aircraft track/heading in degrees from ADS-B."
    )
    # Route from the airport board (cached)
    origin: Optional[str] = Field(None, description="Origin airport ICAO (cached).")
    destination: Optional[str] = Field(None, description="Destination airport ICAO (cached).")
    operator: Optional[str] = Field(None, description="Airline/operator name (cached).")
    # Signal quality tracking
    first_seen_ts: float = Field(
        default_factory=lambda: time.time(), description="Timestamp when plane was first detected."
    )
    update_count: int = Field(
        default=1, description="Number of position updates received for this plane."
    )


class RouteHint(BaseModel):
    """The non-secret part of a plane's route, derived on the server."""

    model_config = ConfigDict(extra="forbid")

    guess_direction: Optional[GuessDirection] = Field(
        description=(
            "Which airport players would guess: 'destination' for a departure from the "
            "monitored airport, 'origin' for an arrival. Null when neither end is the "
            "monitored airport."
        )
    )
    known_airport: Optional[str] = Field(
        description=(
            "ICAO code of the monitored airport when the plane departs from or arrives at it, "
            "otherwise null. The other end is never sent."
        )
    )
    eligible: bool = Field(
        description="Whether the server accepts this plane for a round (selectPlane succeeds)."
    )


class PublicPlaneState(BaseModel):
    """A plane as clients receive it in delta messages.

    The fields are an allowlist copied from the ingested ``PlaneState``, so a
    field added there stays server-side until it is added here on purpose. The
    route's airports are deliberately absent, for every plane: the same delta
    reaches every room, and one end of a playable route is a round's answer.
    """

    model_config = ConfigDict(extra="forbid")

    hex_ident: str = Field(..., description="Aircraft ICAO hex identifier.")
    lat: float = Field(..., description="Smoothed latitude.")
    lon: float = Field(..., description="Smoothed longitude.")
    alt: float = Field(..., description="Smoothed altitude in feet.")
    lat_v: float = Field(..., description="Smoothed latitude velocity.")
    lon_v: float = Field(..., description="Smoothed longitude velocity.")
    alt_v: float = Field(
        ..., description="Smoothed vertical rate in feet per minute, positive when climbing."
    )
    last_update_ts: float = Field(..., description="Timestamp of the last update.")
    trail: List[Tuple[float, float, float]] = Field(
        default_factory=list, description="Recent (lat, lon, alt) tuples, capped at 10."
    )
    callsign: Optional[str] = Field(None, description="Aircraft callsign.")
    track: Optional[float] = Field(None, description="Track/heading in degrees from ADS-B.")
    operator: Optional[str] = Field(None, description="Airline/operator name.")
    first_seen_ts: float = Field(..., description="Timestamp when the plane was first detected.")
    update_count: int = Field(..., description="Number of position updates received.")
    route_hint: RouteHint = Field(..., description="What may be shown about the route.")

"""Response model for GET /api/v0/config: what the browser needs to draw this install's map.

Everything here is static for the life of the process and public. The monitored airport is
already public through every plane's route hint, and no field names a route's airports, so
the config is safe under answer secrecy (PRD §5.2). The fields are copied one by one from
the settings, so a secret setting can only reach browsers by being added here on purpose.
"""

from pydantic import BaseModel, Field


class LatLon(BaseModel):
    """A position in decimal degrees."""

    lat: float = Field(..., ge=-90, le=90, description="Latitude in decimal degrees.")
    lon: float = Field(..., ge=-180, le=180, description="Longitude in decimal degrees.")


class MonitoredAirport(BaseModel):
    """The airport every round is about (MONITORED_AIRPORT_ICAO).

    The airport dataset supplies the other fields. They are null when the airport is not in
    the dataset, which still works for play: answers must be in the dataset, the monitored
    airport need not be.
    """

    icao: str = Field(..., description="ICAO code, e.g. KSEA.")
    iata: str | None = Field(..., description="IATA code, e.g. SEA; null when there is none.")
    name: str | None = Field(..., description="Airport name, e.g. Seattle–Tacoma International.")
    position: LatLon | None = Field(..., description="Where the airport is.")


class ClientConfig(BaseModel):
    """Static settings the browser reads once at startup."""

    center: LatLon = Field(
        ...,
        description=(
            "Where the map opens: the receiver's location (CENTER_LAT, CENTER_LON) rounded "
            "to 2 decimals, about 1 km, so the exact position stays private."
        ),
    )
    monitored_airport: MonitoredAirport
    max_antenna_range_km: float = Field(
        ..., description="Planes farther than this from the centre leave the map."
    )
    map_style_url: str = Field(..., description="MapLibre style URL for the basemap.")
    attributions: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Credits the map must show, one per data source, as HTML (the format TileJSON "
            "and Leaflet use for attributions)."
        ),
    )
    version: str = Field(
        ...,
        description=(
            "The version this install runs, for bug reports: a release image's tag, or "
            "pyproject.toml's version plus the git commit, e.g. 0.1.0-alpha.1+1a2b3c4."
        ),
    )

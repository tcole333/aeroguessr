"""Builds the public config served by GET /api/v0/config from the settings."""

import logging

from backend.schemas.client_config import ClientConfig, LatLon, MonitoredAirport
from backend.settings import Settings
from backend.utils import airport_db
from backend.utils.airport_db import resolve_airport
from backend.version import app_version

logger = logging.getLogger(__name__)

# CENTER_LAT/LON is usually the receiver's home. Two decimals (about 1 km) place the map
# without publishing the exact address.
PUBLIC_CENTER_DECIMALS = 2

# The credit OpenFreeMap publishes in its TileJSON (https://tiles.openfreemap.org/planet). Its
# links open a new tab that gets no handle on the game window. It covers every OpenFreeMap
# style, so MAP_STYLE_URL must stay on OpenFreeMap (or a self-hosted copy) unless this changes.
OPENFREEMAP_ATTRIBUTION = " ".join(
    (
        '<a href="https://openfreemap.org" target="_blank" rel="noopener noreferrer">'
        "OpenFreeMap</a>",
        '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">'
        "&copy; OpenMapTiles</a>",
        'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" '
        'rel="noopener noreferrer">OpenStreetMap</a>',
    )
)


def describe_monitored_airport(icao: str) -> MonitoredAirport:
    """The monitored airport, with its codes, name and position when the dataset has it."""
    airport = resolve_airport(icao)
    if airport is None:
        return MonitoredAirport(icao=icao, iata=None, name=None, position=None)
    return MonitoredAirport(
        icao=icao,
        iata=airport.iata,
        name=airport.name or None,
        position=LatLon(lat=airport.lat, lon=airport.lon),
    )


def warn_if_monitored_airport_unknown(settings: Settings) -> None:
    """Log a warning when MONITORED_AIRPORT_ICAO is not in the airport dataset.

    Play still works, but the map cannot place or label the airport, and a missing code is
    more often a typo than an airport the dataset lacks.
    """
    if resolve_airport(settings.monitored_airport_icao) is None:
        logger.warning(
            "MONITORED_AIRPORT_ICAO=%s is not in %s, so the map cannot label it",
            settings.monitored_airport_icao,
            airport_db.DATA_PATH,
        )


def build_client_config(settings: Settings) -> ClientConfig:
    """The config browsers read at startup."""
    return ClientConfig(
        center=LatLon(
            lat=round(settings.center_lat, PUBLIC_CENTER_DECIMALS),
            lon=round(settings.center_lon, PUBLIC_CENTER_DECIMALS),
        ),
        monitored_airport=describe_monitored_airport(settings.monitored_airport_icao),
        max_antenna_range_km=settings.max_antenna_range_km,
        map_style_url=str(settings.map_style_url),
        attributions=[OPENFREEMAP_ATTRIBUTION],
        version=app_version(settings),
    )

"""GET /api/v0/config: the location and map settings one frontend build reads at startup."""

from html.parser import HTMLParser

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

SEATTLE = {"CENTER_LAT": "47.4502", "CENTER_LON": "-122.3088", "MONITORED_AIRPORT_ICAO": "KSEA"}


class _AttributionHTML(HTMLParser):
    """Collects an attribution's visible text and the attributes of each of its links."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text = ""
        self.links: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.append(dict(attrs))

    def handle_data(self, data: str) -> None:
        self.text += data


def _parse_attributions(body: dict) -> list[_AttributionHTML]:
    parsed = []
    for attribution in body["attributions"]:
        parser = _AttributionHTML()
        parser.feed(attribution)
        parsed.append(parser)
    return parsed


async def _config(client: AsyncClient, monkeypatch: pytest.MonkeyPatch, **env: str) -> dict:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    response = await client.get("/api/v0/config")
    assert response.status_code == 200
    return response.json()


async def test_map_opens_near_the_receiver_without_revealing_its_exact_position(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch, CENTER_LAT="47.450213", CENTER_LON="-122.308791")

    assert body["center"] == {"lat": 47.45, "lon": -122.31}


async def test_monitored_airport_comes_with_its_codes_name_and_position(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch, **SEATTLE)

    assert body["monitored_airport"] == {
        "icao": "KSEA",
        "iata": "SEA",
        "name": "Seattle–Tacoma International Airport",
        "position": {"lat": 47.447943, "lon": -122.310276},
    }


async def test_airport_missing_from_the_dataset_is_named_by_its_code_alone(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch, MONITORED_AIRPORT_ICAO="ZZZZ")

    assert body["monitored_airport"] == {
        "icao": "ZZZZ",
        "iata": None,
        "name": None,
        "position": None,
    }


async def test_config_carries_the_antenna_range(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch, MAX_ANTENNA_RANGE_KM="150")

    assert body["max_antenna_range_km"] == 150


async def test_map_style_defaults_to_openfreemap_positron(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MAP_STYLE_URL", raising=False)

    body = await _config(test_client, monkeypatch)

    assert body["map_style_url"] == "https://tiles.openfreemap.org/styles/positron"


async def test_map_style_comes_from_the_setting(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    liberty = "https://tiles.openfreemap.org/styles/liberty"

    body = await _config(test_client, monkeypatch, MAP_STYLE_URL=liberty)

    assert body["map_style_url"] == liberty


async def test_map_credits_openfreemap_openmaptiles_and_openstreetmap(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch)

    texts = [attribution.text for attribution in _parse_attributions(body)]

    assert "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" in texts


async def test_credit_links_open_a_new_tab_with_no_handle_on_the_game_window(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch)

    links = [link for parsed in _parse_attributions(body) for link in parsed.links]

    assert links and all(
        link.get("target") == "_blank"
        and {"noopener", "noreferrer"} <= set((link.get("rel") or "").split())
        for link in links
    )


async def test_config_names_the_release_an_image_was_built_for(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Release images get their version as BUILD_VERSION, so one pulled as latest says which."""
    body = await _config(test_client, monkeypatch, BUILD_VERSION="0.2.0-beta.1")

    assert body["version"] == "0.2.0-beta.1"


async def test_config_sends_only_its_public_fields(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = await _config(test_client, monkeypatch)

    assert set(body) == {
        "center",
        "monitored_airport",
        "max_antenna_range_km",
        "map_style_url",
        "attributions",
        "version",
    }


async def test_config_leaks_no_secret_setting(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FLIGHTAWARE_API_KEY", "secret-aeroapi-key")
    monkeypatch.setenv("REDIS_URL", "redis://:secret-redis-password@127.0.0.1:6379/0")

    response = await test_client.get("/api/v0/config")

    assert "secret" not in response.text

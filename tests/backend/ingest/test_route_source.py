"""Which route source and refresher the ingest builds for each configuration."""

from dataclasses import replace

import pytest

from backend.ingest.airport_board import AirportBoard, FakeAirportBoard
from backend.ingest.board_refresher import BoardRefresher, build_route_source
from backend.ingest.enrichment_config import EnrichmentConfig
from backend.utils.redis_async import RedisClient

LIVE = EnrichmentConfig(api_key="test-key")


def test_a_key_and_valid_config_start_the_board_refresher() -> None:
    routes, refresher = build_route_source(LIVE, RedisClient())

    assert isinstance(routes, AirportBoard)
    assert isinstance(refresher, BoardRefresher)


@pytest.mark.parametrize(
    "config",
    [
        replace(LIVE, api_key=""),
        replace(LIVE, enabled=False),
        replace(LIVE, errors=("bad cap",)),
    ],
    ids=["no_api_key", "disabled", "config_invalid"],
)
def test_no_refresher_without_a_usable_configuration(config: EnrichmentConfig) -> None:
    routes, refresher = build_route_source(config, RedisClient())

    assert isinstance(routes, AirportBoard)
    assert refresher is None


def test_demo_mode_uses_the_fake_board_even_with_a_key() -> None:
    routes, refresher = build_route_source(replace(LIVE, fake_adsb=True), RedisClient())

    assert isinstance(routes, FakeAirportBoard)
    assert refresher is None

"""Enrichment configuration: budget-derived caps and validation."""

import logging
from decimal import Decimal

import pytest

from backend.ingest.enrichment_config import (
    COLD_START_RESULT_SETS,
    EnrichmentConfig,
    derive_daily_result_set_cap,
)
from backend.ingest.enrichment_gate import GateReason, static_gate_reason


def test_default_budget_allows_25_result_sets_a_day() -> None:
    """$5/month with a 20% margin is $4 = 800 result sets, over 31 days."""
    config = EnrichmentConfig.from_env({})

    assert config.daily_result_set_cap == 25
    assert config.result_sets_per_minute == 8
    assert config.idle_cutoff_seconds == 15 * 60
    assert config.errors == ()


def test_idle_cutoff_can_be_shortened() -> None:
    config = EnrichmentConfig.from_env({"ENRICHMENT_IDLE_CUTOFF_MINUTES": "5"})

    assert config.idle_cutoff_seconds == 300
    assert config.errors == ()


def test_default_budget_raises_no_warning() -> None:
    assert EnrichmentConfig.from_env({}).warnings == ()


def test_implausibly_large_budget_is_logged_as_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """500 typed for 5.00 raises the cap a hundredfold; the owner should see it."""
    config = EnrichmentConfig.from_env({"AEROAPI_MONTHLY_BUDGET_USD": "500"})

    with caplog.at_level(logging.INFO, logger="backend.ingest.enrichment_config"):
        config.log_summary()

    assert config.errors == ()
    assert config.daily_result_set_cap == 2580
    assert any(
        r.levelname == "WARNING" and "AEROAPI_MONTHLY_BUDGET_USD" in r.message
        for r in caplog.records
    )


def test_daily_cap_scales_with_the_budget() -> None:
    assert derive_daily_result_set_cap(Decimal("10.00"), Decimal("0.20")) == 51
    assert derive_daily_result_set_cap(Decimal("0"), Decimal("0.20")) == 0


def test_lower_daily_cap_override_is_accepted() -> None:
    config = EnrichmentConfig.from_env({"AEROAPI_DAILY_RESULT_SET_CAP": "10"})

    assert config.daily_result_set_cap == 10
    assert config.errors == ()


@pytest.mark.parametrize(
    "env",
    [
        {"AEROAPI_DAILY_RESULT_SET_CAP": "26"},
        {"AEROAPI_DAILY_RESULT_SET_CAP": "many"},
        {"AEROAPI_DAILY_RESULT_SET_CAP": "-1"},
        {"AEROAPI_MONTHLY_BUDGET_USD": "-5"},
        {"AEROAPI_MONTHLY_BUDGET_USD": "five"},
        {"AEROAPI_MONTHLY_BUDGET_USD": "NaN"},
        {"AEROAPI_BUDGET_SAFETY_MARGIN": "1"},
        {"AEROAPI_RESULT_SETS_PER_MINUTE": "11"},
        {"AEROAPI_RESULT_SETS_PER_MINUTE": "0"},
        {"ENRICHMENT_IDLE_CUTOFF_MINUTES": "0"},
        {"ENRICHMENT_IDLE_CUTOFF_MINUTES": "nan"},
        {"ENRICHMENT_ENABLED": "n"},
        {"ENRICHMENT_ENABLED": "disable"},
        {"FAKE_ADSB": "y"},
        {"MONITORED_AIRPORT_ICAO": "BOS"},
        {"MONITORED_AIRPORT_ICAO": "kbos"},
        {"MONITORED_AIRPORT_ICAO": " KBOS"},
    ],
)
def test_invalid_settings_are_reported(env: dict[str, str]) -> None:
    assert EnrichmentConfig.from_env(env).errors


@pytest.mark.parametrize("value", ["n", "none", "disable", '"0"'])
def test_unrecognised_enrichment_switch_keeps_the_gate_closed(value: str) -> None:
    """A typo in the cost kill switch must not leave paid refreshes running."""
    config = EnrichmentConfig.from_env({"ENRICHMENT_ENABLED": value, "FLIGHTAWARE_API_KEY": "k"})

    assert static_gate_reason(config) is GateReason.CONFIG_INVALID


@pytest.mark.parametrize("per_minute", range(1, COLD_START_RESULT_SETS))
def test_per_minute_limit_below_one_board_fill_is_rejected(per_minute: int) -> None:
    """A limit that can never fund the first fill would silently disable enrichment."""
    config = EnrichmentConfig.from_env({"AEROAPI_RESULT_SETS_PER_MINUTE": str(per_minute)})

    assert config.errors


def test_per_minute_limit_of_one_board_fill_is_accepted() -> None:
    config = EnrichmentConfig.from_env(
        {"AEROAPI_RESULT_SETS_PER_MINUTE": str(COLD_START_RESULT_SETS)}
    )

    assert config.errors == ()


@pytest.mark.parametrize("cap", range(1, COLD_START_RESULT_SETS))
def test_daily_cap_below_one_board_fill_is_rejected(cap: int) -> None:
    assert EnrichmentConfig.from_env({"AEROAPI_DAILY_RESULT_SET_CAP": str(cap)}).errors


def test_budget_too_small_for_one_board_fill_is_rejected() -> None:
    """$0.80 a month derives a daily cap of 4 result sets."""
    assert EnrichmentConfig.from_env({"AEROAPI_MONTHLY_BUDGET_USD": "0.80"}).errors


def test_zero_daily_cap_turns_spending_off_without_an_error() -> None:
    config = EnrichmentConfig.from_env({"AEROAPI_DAILY_RESULT_SET_CAP": "0"})

    assert config.daily_result_set_cap == 0
    assert config.errors == ()


def test_config_errors_are_logged_at_error(caplog: pytest.LogCaptureFixture) -> None:
    EnrichmentConfig.from_env({"AEROAPI_DAILY_RESULT_SET_CAP": "500"}).log_summary()

    assert any(
        r.levelname == "ERROR" and "AEROAPI_DAILY_RESULT_SET_CAP" in r.message
        for r in caplog.records
    )


def test_flags_and_key_are_read_tolerantly() -> None:
    config = EnrichmentConfig.from_env(
        {
            "ENRICHMENT_ENABLED": "off",
            "FAKE_ADSB": "true",
            "FLIGHTAWARE_API_KEY": "  test-key  ",
            "MONITORED_AIRPORT_ICAO": "KJFK",
        }
    )

    assert config.enabled is False
    assert config.fake_adsb is True
    assert config.api_key == "test-key"
    assert config.airport_icao == "KJFK"
    assert config.errors == ()


def test_api_key_never_appears_in_repr_or_summary(caplog: pytest.LogCaptureFixture) -> None:
    config = EnrichmentConfig.from_env({"FLIGHTAWARE_API_KEY": "test-secret-value"})
    config.log_summary()

    assert "test-secret-value" not in repr(config)
    assert "test-secret-value" not in caplog.text

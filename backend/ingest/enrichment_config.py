"""Configuration for FlightAware AeroAPI airport-board enrichment.

Every spend limit is derived from a monthly dollar budget so the owner only
has to reason about money. Invalid settings never fall back to a guess: they
are collected in ``errors`` and keep the enrichment gate closed.
"""

import logging
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal, InvalidOperation

from backend.utils.env import FLAG_SPELLINGS, env_flag

logger = logging.getLogger(__name__)

# FlightAware bills $0.005 per result set (15 records); multi-page responses
# bill every page returned.
COST_PER_RESULT_SET_USD = Decimal("0.005")
# The daily cap times this must fit the monthly budget, so assume the longest month.
BILLING_PERIOD_DAYS = 31
# AeroAPI Personal tier limit.
PERSONAL_TIER_RESULT_SETS_PER_MINUTE = 10

DEFAULT_MONTHLY_BUDGET_USD = Decimal("5.00")
# A budget above this is accepted but logged as a WARNING: it is more likely a
# typo (500 for 5.00) than intended for a game played a few minutes a week.
HIGH_BUDGET_WARNING_USD = Decimal("20.00")
DEFAULT_SAFETY_MARGIN = Decimal("0.20")
DEFAULT_RESULT_SETS_PER_MINUTE = 8
DEFAULT_IDLE_CUTOFF_MINUTES = 15.0
DEFAULT_AIRPORT_ICAO = "KBOS"
# Board rows are matched against MONITORED_AIRPORT_ICAO verbatim and the code
# goes into the AeroAPI URL, so only the canonical form is accepted here.
_ICAO_CODE = re.compile(r"^[A-Z]{4}$")

# Pages the board refresher reserves per request. A cold start (empty board)
# asks for arrivals, scheduled departures and recent departures in one tick.
ARRIVALS_COLD_PAGES = 2
DEPARTURES_COLD_PAGES = 2
RECENT_DEPARTURES_PAGES = 1
WARM_PAGES = 1
COLD_START_RESULT_SETS = ARRIVALS_COLD_PAGES + DEPARTURES_COLD_PAGES + RECENT_DEPARTURES_PAGES


def derive_daily_result_set_cap(monthly_budget_usd: Decimal, safety_margin: Decimal) -> int:
    """Largest daily cap whose 31-day total stays within the budget minus the margin."""
    spendable = monthly_budget_usd * (Decimal(1) - safety_margin)
    per_day = spendable / COST_PER_RESULT_SET_USD / BILLING_PERIOD_DAYS
    return int(per_day.to_integral_value(rounding=ROUND_FLOOR))


@dataclass(frozen=True)
class EnrichmentConfig:
    """Effective enrichment settings for the ingest process."""

    enabled: bool = True
    api_key: str = field(default="", repr=False)
    fake_adsb: bool = False
    airport_icao: str = DEFAULT_AIRPORT_ICAO
    idle_cutoff_seconds: float = DEFAULT_IDLE_CUTOFF_MINUTES * 60
    daily_result_set_cap: int = derive_daily_result_set_cap(
        DEFAULT_MONTHLY_BUDGET_USD, DEFAULT_SAFETY_MARGIN
    )
    result_sets_per_minute: int = DEFAULT_RESULT_SETS_PER_MINUTE
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "EnrichmentConfig":
        """Build the config from ``Settings.enrichment_environ()``, collecting any errors."""
        errors: list[str] = []

        budget = _parse_decimal(env, "AEROAPI_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD)
        margin = _parse_decimal(env, "AEROAPI_BUDGET_SAFETY_MARGIN", DEFAULT_SAFETY_MARGIN)
        if budget is None or budget < 0:
            errors.append("AEROAPI_MONTHLY_BUDGET_USD must be a non-negative number")
        if margin is None or not Decimal(0) <= margin < Decimal(1):
            errors.append("AEROAPI_BUDGET_SAFETY_MARGIN must be at least 0 and below 1")
        warnings = []
        if budget is not None and budget > HIGH_BUDGET_WARNING_USD:
            warnings.append(
                f"AEROAPI_MONTHLY_BUDGET_USD is ${budget}, above ${HIGH_BUDGET_WARNING_USD}; "
                "check it is not a typo"
            )

        derived_cap = 0
        if budget is not None and margin is not None and not errors:
            derived_cap = derive_daily_result_set_cap(budget, margin)
        daily_cap = derived_cap
        if _is_set(env, "AEROAPI_DAILY_RESULT_SET_CAP") and not errors:
            override = _parse_int(env, "AEROAPI_DAILY_RESULT_SET_CAP", derived_cap)
            if override is None or not 0 <= override <= derived_cap:
                errors.append(
                    "AEROAPI_DAILY_RESULT_SET_CAP must be a whole number from 0 to "
                    f"{derived_cap}, the most the monthly budget allows"
                )
            else:
                daily_cap = override
        if not errors and 0 < daily_cap < COLD_START_RESULT_SETS:
            errors.append(
                f"a daily cap of {daily_cap} result sets cannot fund one board fill "
                f"({COLD_START_RESULT_SETS}); raise AEROAPI_MONTHLY_BUDGET_USD or "
                "AEROAPI_DAILY_RESULT_SET_CAP, or set the cap to 0 to turn enrichment off"
            )

        per_minute = _parse_int(
            env, "AEROAPI_RESULT_SETS_PER_MINUTE", DEFAULT_RESULT_SETS_PER_MINUTE
        )
        if per_minute is None or not (
            COLD_START_RESULT_SETS <= per_minute <= PERSONAL_TIER_RESULT_SETS_PER_MINUTE
        ):
            errors.append(
                "AEROAPI_RESULT_SETS_PER_MINUTE must be a whole number from "
                f"{COLD_START_RESULT_SETS} (one board fill) to "
                f"{PERSONAL_TIER_RESULT_SETS_PER_MINUTE}"
            )

        cutoff_minutes = _parse_float(
            env, "ENRICHMENT_IDLE_CUTOFF_MINUTES", DEFAULT_IDLE_CUTOFF_MINUTES
        )
        if cutoff_minutes is None or not 0 < cutoff_minutes < math.inf:
            errors.append("ENRICHMENT_IDLE_CUTOFF_MINUTES must be a positive number")

        enabled = env_flag("ENRICHMENT_ENABLED", True, env)
        if enabled is None:
            errors.append(f"ENRICHMENT_ENABLED must be {FLAG_SPELLINGS}")
        fake_adsb = env_flag("FAKE_ADSB", False, env)
        if fake_adsb is None:
            errors.append(f"FAKE_ADSB must be {FLAG_SPELLINGS}")
        airport_icao = env.get("MONITORED_AIRPORT_ICAO") or DEFAULT_AIRPORT_ICAO
        if not _ICAO_CODE.match(airport_icao):
            errors.append(
                "MONITORED_AIRPORT_ICAO must be a 4-letter uppercase ICAO code such as KBOS"
            )

        return cls(
            enabled=bool(enabled),
            api_key=env.get("FLIGHTAWARE_API_KEY", "").strip(),
            fake_adsb=bool(fake_adsb),
            airport_icao=airport_icao,
            idle_cutoff_seconds=(cutoff_minutes or DEFAULT_IDLE_CUTOFF_MINUTES) * 60,
            daily_result_set_cap=daily_cap,
            result_sets_per_minute=per_minute or DEFAULT_RESULT_SETS_PER_MINUTE,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    def log_summary(self) -> None:
        """Log the effective limits at INFO, warnings at WARNING and errors at ERROR."""
        logger.info(
            "AeroAPI enrichment: enabled=%s key_configured=%s fake_adsb=%s airport=%s "
            "daily_cap=%d result sets ($%s) per_minute=%d idle_cutoff=%.0fs",
            self.enabled,
            bool(self.api_key),
            self.fake_adsb,
            self.airport_icao,
            self.daily_result_set_cap,
            self.daily_result_set_cap * COST_PER_RESULT_SET_USD,
            self.result_sets_per_minute,
            self.idle_cutoff_seconds,
        )
        for warning in self.warnings:
            logger.warning("AeroAPI enrichment config: %s", warning)
        for error in self.errors:
            logger.error("Invalid AeroAPI enrichment config, enrichment stays off: %s", error)


def _is_set(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def _parse_decimal(env: Mapping[str, str], name: str, default: Decimal) -> Decimal | None:
    if not _is_set(env, name):
        return default
    try:
        value = Decimal(env[name].strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def _parse_int(env: Mapping[str, str], name: str, default: int) -> int | None:
    if not _is_set(env, name):
        return default
    try:
        return int(env[name].strip())
    except ValueError:
        return None


def _parse_float(env: Mapping[str, str], name: str, default: float) -> float | None:
    if not _is_set(env, name):
        return default
    try:
        return float(env[name].strip())
    except ValueError:
        return None

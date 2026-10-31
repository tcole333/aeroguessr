"""Every environment setting the API and ingest read, with its default.

Values come from the process environment first, then from the repo-root ``.env``.
Containers get their environment from Compose and have no ``.env``. Set
``AEROGUESSR_ENV_FILE`` to read another file, or to an empty value to read none;
the test suite reads none.

An empty value counts as unset: an empty environment variable falls through to
``.env``, and an empty ``.env`` value to the default. So a blank kill switch such as
``FAKE_ADSB=`` keeps whatever ``.env`` says rather than reverting to live mode. The one
exception is ``FLIGHTAWARE_API_KEY=`` in the environment, which always means "no key",
even when ``.env`` holds one.

The AeroAPI spend settings stay raw strings. ``EnrichmentConfig`` validates them,
and an invalid one keeps enrichment off instead of stopping the process. Every
other invalid value stops the process at startup with a ``ValidationError``.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_VARIABLE = "AEROGUESSR_ENV_FILE"
OPENFREEMAP_POSITRON_STYLE_URL = "https://tiles.openfreemap.org/styles/positron"


def env_file() -> Path | None:
    """The ``.env`` to read: ``AEROGUESSR_ENV_FILE`` if set (empty: none), else the repo root's."""
    configured = os.environ.get(ENV_FILE_VARIABLE)
    if configured is None:
        return REPO_ROOT / ".env"
    return Path(configured) if configured.strip() else None


class Settings(BaseSettings):
    """Backend settings. Field names are the environment variable names, lower-cased."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True, env_ignore_empty=True)

    # Shared
    redis_url: str = "redis://localhost:6379/0"
    redis_socket_connect_timeout_seconds: float = Field(5, gt=0)
    redis_socket_timeout_seconds: float = Field(5, gt=0)
    log_level: str | None = None  # ingest only; unknown levels log a warning and use INFO

    # Ingest: the ADS-B feed and plane storage
    adsb_host: str = "127.0.0.1"
    adsb_port: int = Field(30003, ge=1, le=65535)
    center_lat: float = Field(42.3656, ge=-90, le=90)
    center_lon: float = Field(-71.0096, ge=-180, le=180)
    plane_ttl_seconds: int = Field(300, gt=0)
    fake_adsb_file: str = "synthetic"  # or the path of an SBS-1 capture to replay
    fake_adsb_speed: float = Field(1.0, gt=0)
    syn_plane_count: int = Field(3, ge=1)

    # API
    max_antenna_range_km: float = Field(250, gt=0)
    min_update_interval_seconds: int = Field(60, gt=0)
    ingest_health_threshold_seconds: float = Field(60, gt=0)
    host_disconnect_claim_window_seconds: int = Field(120, ge=0)
    ws_base_url: str | None = None
    monitored_airport_icao: str = Field("KBOS", pattern=r"^[A-Z]{4}$")
    map_style_url: HttpUrl = HttpUrl(OPENFREEMAP_POSITRON_STYLE_URL)  # sent to browsers
    build_version: str | None = None  # release images set their version; see backend/version.py

    # AeroAPI spend, validated by EnrichmentConfig (see enrichment_environ)
    flightaware_api_key: str | None = Field(None, repr=False)
    enrichment_enabled: str | None = None
    fake_adsb: str | None = None
    enrichment_idle_cutoff_minutes: str | None = None
    aeroapi_monthly_budget_usd: str | None = None
    aeroapi_budget_safety_margin: str | None = None
    aeroapi_daily_result_set_cap: str | None = None
    aeroapi_result_sets_per_minute: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_means_default(cls, value: object, info: ValidationInfo) -> object:
        """Use the default for a whitespace-only value; AeroAPI raw strings stay as they are."""
        if not isinstance(value, str) or value.strip():
            return value
        if info.field_name in _RAW_ENRICHMENT_FIELDS:
            return value
        return cls.model_fields[info.field_name].get_default()

    def enrichment_environ(self) -> dict[str, str]:
        """The settings ``EnrichmentConfig.from_env`` reads, keyed by variable name."""
        names = (*_RAW_ENRICHMENT_FIELDS, "monitored_airport_icao")
        values = {name.upper(): getattr(self, name) for name in names}
        return {name: value for name, value in values.items() if value is not None}


_RAW_ENRICHMENT_FIELDS = (
    "flightaware_api_key",
    "enrichment_enabled",
    "fake_adsb",
    "enrichment_idle_cutoff_minutes",
    "aeroapi_monthly_budget_usd",
    "aeroapi_budget_safety_margin",
    "aeroapi_daily_result_set_cap",
    "aeroapi_result_sets_per_minute",
)


def load_settings() -> Settings:
    """Read the settings now, from the environment and the ``.env`` file."""
    overrides: dict[str, str] = {}
    # A key blanked in the environment wins over .env: it is how a run turns AeroAPI off.
    environment_key = os.environ.get("FLIGHTAWARE_API_KEY")
    if environment_key is not None and not environment_key.strip():
        overrides["flightaware_api_key"] = ""
    return Settings(_env_file=env_file(), **overrides)  # type: ignore[call-arg]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process's settings, read once. Clear with ``get_settings.cache_clear()``."""
    return load_settings()

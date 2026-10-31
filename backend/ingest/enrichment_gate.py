"""Decides whether the ingest may spend money on AeroAPI right now.

All of these must hold: enrichment is enabled, an API key is configured, the
feed is real (not FAKE_ADSB), the config is valid, Redis is reachable, a
player is connected, and someone did something that counts as playing within
the idle cutoff. Anything else keeps the gate closed.
"""

import logging
import time
from collections.abc import Callable
from enum import StrEnum

from backend.ingest.enrichment_config import EnrichmentConfig
from backend.services.presence import read_presence
from backend.utils.redis_async import RedisClient

logger = logging.getLogger(__name__)


class GateReason(StrEnum):
    """The gate's verdict; anything but OPEN means no AeroAPI request."""

    OPEN = "open"
    DISABLED = "disabled"
    NO_API_KEY = "no_api_key"
    FAKE_ADSB = "fake_adsb"
    CONFIG_INVALID = "config_invalid"
    REDIS_ERROR = "redis_error"
    NO_PLAYERS = "no_players"
    IDLE = "idle"


def static_gate_reason(config: EnrichmentConfig) -> GateReason | None:
    """The reason configuration alone keeps the gate closed, if any."""
    if config.errors:
        return GateReason.CONFIG_INVALID
    if not config.enabled:
        return GateReason.DISABLED
    if not config.api_key:
        return GateReason.NO_API_KEY
    if config.fake_adsb:
        return GateReason.FAKE_ADSB
    return None


class EnrichmentGate:
    """Evaluates the gate from config plus the presence signals in Redis."""

    def __init__(
        self,
        redis_client: RedisClient,
        config: EnrichmentConfig,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis_client
        self._config = config
        self._clock = clock

    async def evaluate(self) -> GateReason:
        static_reason = static_gate_reason(self._config)
        if static_reason is not None:
            return static_reason
        try:
            presence = await read_presence(self._redis)
        except Exception as e:
            logger.warning("Cannot read player presence, keeping AeroAPI off: %s", e)
            return GateReason.REDIS_ERROR
        if presence.active_rooms < 1:
            return GateReason.NO_PLAYERS
        last_activity = presence.last_activity_ts
        if (
            last_activity is None
            or self._clock() - last_activity > self._config.idle_cutoff_seconds
        ):
            return GateReason.IDLE
        return GateReason.OPEN

"""Process-wide logging setup for entry points that are not run under uvicorn."""

import logging

from backend.settings import get_settings


def parse_log_level(raw: str | None) -> int | None:
    """Map a LOG_LEVEL string such as ``"debug"`` to a logging level, or None if unknown."""
    if not raw or not raw.strip():
        return None
    level = logging.getLevelName(raw.strip().upper())
    return level if isinstance(level, int) else None


def configure_logging(service: str) -> None:
    """Configure root logging for ``service`` from LOG_LEVEL (default INFO)."""
    raw_level = get_settings().log_level
    level = parse_log_level(raw_level)
    logging.basicConfig(
        level=level if level is not None else logging.INFO,
        format=f"%(asctime)s %(levelname)s [{service}] %(name)s: %(message)s",
        force=True,
    )
    if raw_level and level is None:
        logging.getLogger(__name__).warning("Unknown LOG_LEVEL %r; using INFO", raw_level)

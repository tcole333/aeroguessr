"""Environment variable parsing helpers shared by the API and ingest processes."""

from collections.abc import Mapping

TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
FALSE_VALUES = frozenset({"0", "false", "no", "off"})
FLAG_SPELLINGS = "1/true/yes/on or 0/false/no/off"


def env_flag(name: str, default: bool, environ: Mapping[str, str]) -> bool | None:
    """Read a boolean flag, accepting 1/true/yes/on and 0/false/no/off (any case).

    An unset or empty variable yields ``default``. Any other value yields
    ``None`` so the caller can reject it rather than guess what a typo meant.
    """
    raw = environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in TRUE_VALUES:
        return True
    if value in FALSE_VALUES:
        return False
    return None

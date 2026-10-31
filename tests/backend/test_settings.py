"""Settings come from the environment, then the .env file, then the defaults in settings.py."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.ingest.enrichment_config import EnrichmentConfig
from backend.settings import ENV_FILE_VARIABLE, REPO_ROOT, Settings, env_file, load_settings


@pytest.fixture
def dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty .env file that load_settings reads, with no competing variables set."""
    path = tmp_path / ".env"
    path.write_text("")
    monkeypatch.setenv(ENV_FILE_VARIABLE, str(path))
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    return path


def test_reads_a_setting_from_the_env_file(dotenv: Path) -> None:
    dotenv.write_text("ADSB_PORT=31000\n")

    assert load_settings().adsb_port == 31000


def test_environment_overrides_the_env_file(dotenv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv.write_text("ADSB_PORT=31000\n")
    monkeypatch.setenv("ADSB_PORT", "32000")

    assert load_settings().adsb_port == 32000


def test_empty_key_in_the_environment_turns_aeroapi_off_despite_a_key_in_the_env_file(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("FLIGHTAWARE_API_KEY=real-looking-key\n")
    monkeypatch.setenv("FLIGHTAWARE_API_KEY", "")

    config = EnrichmentConfig.from_env(load_settings().enrichment_environ())

    assert config.api_key == ""


def test_blank_environment_variable_falls_through_to_the_env_file(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dotenv.write_text("ADSB_PORT=31000\n")
    monkeypatch.setenv("ADSB_PORT", "")

    assert load_settings().adsb_port == 31000


def test_blank_everywhere_uses_the_default(dotenv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv.write_text("ADSB_PORT=\n")
    monkeypatch.setenv("ADSB_PORT", "")

    assert load_settings().adsb_port == 30003


def test_key_in_the_env_file_is_used(dotenv: Path) -> None:
    dotenv.write_text("FLIGHTAWARE_API_KEY=from-env-file\n")

    config = EnrichmentConfig.from_env(load_settings().enrichment_environ())

    assert config.api_key == "from-env-file"


SAFE_ENV_FILE = (
    "FLIGHTAWARE_API_KEY=real-looking-key\n"
    "FAKE_ADSB=1\n"
    "ENRICHMENT_ENABLED=false\n"
    "AEROAPI_DAILY_RESULT_SET_CAP=0\n"
)


@pytest.mark.parametrize(
    ("blanked", "still_safe"),
    [
        ("FAKE_ADSB", lambda config: config.fake_adsb),
        ("ENRICHMENT_ENABLED", lambda config: not config.enabled),
        ("AEROAPI_DAILY_RESULT_SET_CAP", lambda config: config.daily_result_set_cap == 0),
    ],
)
def test_blank_kill_switch_in_the_environment_keeps_the_env_files_safe_value(
    dotenv: Path,
    monkeypatch: pytest.MonkeyPatch,
    blanked: str,
    still_safe: Callable[[EnrichmentConfig], bool],
) -> None:
    dotenv.write_text(SAFE_ENV_FILE)
    monkeypatch.setenv(blanked, "")

    config = EnrichmentConfig.from_env(load_settings().enrichment_environ())

    assert still_safe(config)


def test_demo_feed_defaults_to_synthetic_planes(dotenv: Path) -> None:
    """FAKE_ADSB=1 alone must show planes; a replay of a capture made elsewhere shows none."""
    assert load_settings().fake_adsb_file == "synthetic"


def test_invalid_setting_stops_startup(dotenv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADSB_PORT", "thirty")

    with pytest.raises(ValidationError):
        load_settings()


def test_monitored_airport_must_be_an_icao_code(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MONITORED_AIRPORT_ICAO", "bos")

    with pytest.raises(ValidationError):
        load_settings()


@pytest.mark.parametrize("value", ["tiles.openfreemap.org/styles/positron", "ftp://tiles/x"])
def test_map_style_url_must_be_an_http_url(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAP_STYLE_URL", value)

    with pytest.raises(ValidationError):
        load_settings()


def test_invalid_spend_setting_keeps_enrichment_off_instead_of_stopping(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AEROAPI_MONTHLY_BUDGET_USD", "lots")

    config = EnrichmentConfig.from_env(load_settings().enrichment_environ())

    assert config.errors


def test_api_key_is_left_out_of_the_repr(dotenv: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLIGHTAWARE_API_KEY", "secret-value")

    assert "secret-value" not in repr(load_settings())


def test_the_test_suite_reads_no_env_file() -> None:
    """tests/conftest.py keeps a developer's .env, which may hold a real key, out of every test."""
    assert env_file() is None


class _RecordingEnviron(dict[str, str]):
    """An empty environment that records every variable name looked up in it."""

    def __init__(self) -> None:
        super().__init__()
        self.names: set[str] = set()

    def get(self, key: str, default: str | None = None) -> str | None:  # type: ignore[override]
        self.names.add(key)
        return super().get(key, default)


def test_settings_pass_on_every_variable_enrichment_config_reads(
    dotenv: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    environ = _RecordingEnviron()
    EnrichmentConfig.from_env(environ)
    for name in environ.names:
        monkeypatch.setenv(name, "KBOS" if name == "MONITORED_AIRPORT_ICAO" else "1")

    assert environ.names <= set(load_settings().enrichment_environ())


def test_empty_env_file_variable_reads_no_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_FILE_VARIABLE, "")

    assert env_file() is None


def test_env_file_defaults_to_the_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_FILE_VARIABLE)

    assert env_file() == REPO_ROOT / ".env"


@pytest.mark.parametrize("name", sorted(field.upper() for field in Settings.model_fields))
def test_env_example_documents_the_setting(name: str) -> None:
    example = (REPO_ROOT / ".env.example").read_text()

    assert re.search(rf"^#?\s*{name}=", example, re.MULTILINE)

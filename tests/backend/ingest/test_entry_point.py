"""The ingest process, started the way Docker starts it, logs at LOG_LEVEL (default INFO).

Redis is unreachable on purpose: the process logs its enrichment summary, fails
to reach Redis and exits, so no server and no network access are needed.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_ingest(tmp_path: Path, **extra_env: str) -> str:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "AEROGUESSR_ENV_FILE": "",  # never the developer's .env
        "PYTHONPATH": str(REPO_ROOT),
        "REDIS_URL": "redis://127.0.0.1:1/9",  # nothing listens here
        "FAKE_ADSB": "0",
        "FLIGHTAWARE_API_KEY": "",
        **extra_env,
    }
    result = subprocess.run(
        [sys.executable, "-m", "backend.ingest.main"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stderr


def test_ingest_logs_at_info_without_log_level(tmp_path: Path) -> None:
    stderr = _run_ingest(tmp_path)

    assert "INFO [ingest]" in stderr
    assert "AeroAPI enrichment: enabled=True key_configured=False" in stderr


@pytest.mark.parametrize("level", ["warning", "ERROR"])
def test_ingest_honours_log_level(tmp_path: Path, level: str) -> None:
    stderr = _run_ingest(tmp_path, LOG_LEVEL=level)

    assert "INFO [ingest]" not in stderr
    assert "ERROR [ingest]" in stderr  # the Redis failure still shows

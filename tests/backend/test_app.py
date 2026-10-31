"""Tests for main app endpoints."""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from backend import app as app_module
from backend.app import lifespan
from backend.utils import airport_db


@pytest.mark.asyncio
async def test_root_endpoint(test_client: AsyncClient) -> None:
    """Test root endpoint returns welcome message."""
    response = await test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "AeroGuessr" in data["message"]


def test_api_process_never_loads_the_ingest_or_an_http_client() -> None:
    """Only the ingest may reach AeroAPI, so the API process must not even import its client.

    A fresh interpreter, because other tests in this process import the ingest.
    """
    probe = (
        "import sys, backend.app; "
        "print(sorted(m for m in sys.modules if m.startswith(('backend.ingest', 'httpx'))))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "AEROGUESSR_ENV_FILE": ""},
    )

    assert result.stdout.strip() == "[]"


@pytest.mark.asyncio
async def test_startup_fails_without_airport_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The API refuses to start rather than score every guess against no airports."""
    monkeypatch.setattr(airport_db, "DATA_PATH", tmp_path / "missing.json")
    fresh_app = FastAPI()

    with pytest.raises(FileNotFoundError):
        async with lifespan(fresh_app):
            pass

    assert not getattr(fresh_app.state, "broadcast_started", False)


@pytest.mark.asyncio
@pytest.mark.parametrize(("icao", "warns"), [("ZZZZ", True), ("KSEA", False)])
async def test_startup_warns_when_the_monitored_airport_is_not_in_the_dataset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, icao: str, warns: bool
) -> None:
    """A code the dataset lacks still plays, but the map cannot label it: usually a typo."""

    async def idle_broadcast(*_args: object) -> None:
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module, "broadcast_plane_updates", idle_broadcast)
    monkeypatch.setenv("MONITORED_AIRPORT_ICAO", icao)

    with caplog.at_level(logging.WARNING):
        async with lifespan(FastAPI()):
            pass

    assert any(f"MONITORED_AIRPORT_ICAO={icao}" in r.getMessage() for r in caplog.records) is warns

"""Tests for ingest logging configuration."""

import logging
from collections.abc import Iterator

import pytest

from backend.utils.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    saved_level, saved_handlers = root.level, list(root.handlers)
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging("ingest")
    assert logging.getLogger().level == logging.INFO


def test_honours_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "debug")
    configure_logging("ingest")
    assert logging.getLogger().level == logging.DEBUG


def test_unknown_level_falls_back_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "chatty")
    configure_logging("ingest")
    assert logging.getLogger().level == logging.INFO


def test_records_are_tagged_with_service(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    configure_logging("ingest")
    logging.getLogger("backend.ingest.example").info("usage line")
    assert "INFO [ingest] backend.ingest.example: usage line" in capsys.readouterr().err

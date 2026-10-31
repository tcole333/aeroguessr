"""Importing the app leaves loggers at INFO.

Forcing DEBUG on these loggers wrote every WebSocket frame to the logs, including
guesses and round results, and the broadcast loop logged at INFO every second.
"""

import logging

import pytest

import backend.app  # noqa: F401  (import side effects configure logging)


@pytest.mark.parametrize(
    "name", ["backend.routes.rooms", "backend.services.broadcast", "uvicorn.error"]
)
def test_logger_is_not_forced_to_debug(name: str) -> None:
    assert logging.getLogger(name).getEffectiveLevel() >= logging.INFO

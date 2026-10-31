"""Tests for tolerant environment flag parsing."""

import pytest

from backend.utils.env import env_flag


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "On", " true "])
def test_truthy_spellings_enable_flag(raw: str) -> None:
    assert env_flag("FLAG", False, {"FLAG": raw}) is True


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", "OFF"])
def test_falsy_spellings_disable_flag(raw: str) -> None:
    assert env_flag("FLAG", True, {"FLAG": raw}) is False


@pytest.mark.parametrize("default", [True, False])
def test_unset_or_blank_uses_default(default: bool) -> None:
    assert env_flag("FLAG", default, {}) is default
    assert env_flag("FLAG", default, {"FLAG": "  "}) is default


@pytest.mark.parametrize("raw", ["enabled", "n", "none", '"0"'])
def test_unrecognised_value_is_reported_as_none(raw: str) -> None:
    assert env_flag("FLAG", True, {"FLAG": raw}) is None

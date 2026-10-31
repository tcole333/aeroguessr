"""The version this install reports: in GET /api/v0/config, /healthz and the startup log."""

import subprocess
import tomllib
from functools import lru_cache

from backend.settings import REPO_ROOT, Settings


def app_version(settings: Settings) -> str:
    """BUILD_VERSION when set, else pyproject.toml's version plus the checkout's commit, if any.

    Release images set BUILD_VERSION to their release version, the git tag without its v
    (.github/workflows/release.yml), so an image pulled as ``latest`` still names its release.
    A run from a git checkout reports, for example, ``0.1.0-alpha.1+1a2b3c4``.
    """
    return settings.build_version or _source_version()


@lru_cache(maxsize=1)
def _source_version() -> str:
    version = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]["version"]
    commit = _checkout_commit()
    return f"{version}+{commit}" if commit else version


def _checkout_commit() -> str | None:
    """The checkout's short commit hash; None without git or a checkout, as in an image."""
    # Without this check, code unpacked inside some other repository would report its commit.
    if not (REPO_ROOT / ".git").exists():
        return None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607 (a fixed git command, no input)
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None

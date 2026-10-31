"""The backend, the frontend, the self-hosters' .env template and their guide name one version.

The release workflow (.github/workflows/release.yml) refuses a tag whose version differs from
pyproject.toml and tags the images with it. The template self-hosters download from that tag
pins the same version, so its compose file pulls the images built from it, and the guide's
quickstart downloads that tag.
"""

import json
import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Semver, as the release tags and npm need it: 1.2.3 or 1.2.3-alpha.1.
SEMVER = re.compile(r"\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?")


def _backend_version() -> str:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return pyproject["project"]["version"]


def _json(path: str) -> dict:
    return json.loads((REPO_ROOT / path).read_text())


def _selfhost_pinned_version() -> str | None:
    for line in (REPO_ROOT / "selfhost" / ".env.example").read_text().splitlines():
        if line.startswith("AEROGUESSR_VERSION="):
            return line.split("=", 1)[1]
    return None


def _guide_quickstart_version() -> str | None:
    """The first VERSION= in docs/self-hosting.md, which is the quickstart's."""
    for line in (REPO_ROOT / "docs" / "self-hosting.md").read_text().splitlines():
        if line.startswith("VERSION="):
            return line.split("=", 1)[1].split()[0]
    return None


def test_version_is_semver() -> None:
    assert SEMVER.fullmatch(_backend_version())


def test_frontend_package_has_the_backend_version() -> None:
    assert _json("frontend/package.json")["version"] == _backend_version()


def test_frontend_lockfile_has_the_backend_version() -> None:
    lockfile = _json("frontend/package-lock.json")

    assert {lockfile["version"], lockfile["packages"][""]["version"]} == {_backend_version()}


def test_selfhost_env_template_pins_the_current_version() -> None:
    assert _selfhost_pinned_version() == _backend_version()


def test_self_hosting_quickstart_installs_the_current_version() -> None:
    assert _guide_quickstart_version() == _backend_version()

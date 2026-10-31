"""scripts/checkout-env.sh gives each checkout its own Compose project and free ports.

Each test runs the real script with bash.
"""

import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "checkout-env.sh"


@pytest.fixture
def busy_port() -> Iterator[int]:
    """A port something listens on, with room for a scan above it."""
    while True:
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        if listener.getsockname()[1] < 65000:
            break
        listener.close()
    with listener:
        listener.listen()
        yield listener.getsockname()[1]


def test_each_checkout_gets_a_compose_project_named_after_its_directory(tmp_path: Path) -> None:
    env = {name: value for name, value in os.environ.items() if name != "COMPOSE_PROJECT_NAME"}
    projects = []
    for checkout in ("plane-game-v4", "Peaceful Hamilton_2.test"):
        scripts = tmp_path / checkout / "scripts"
        scripts.mkdir(parents=True)
        shutil.copy(SCRIPT, scripts)
        result = subprocess.run(
            ["bash", str(scripts / SCRIPT.name), "project"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        projects.append(result.stdout.strip())

    assert projects == ["aeroguessr-plane-game-v4", "aeroguessr-peaceful-hamilton-2-test"]


def test_free_port_skips_ports_in_use_and_reserved_ports(busy_port: int) -> None:
    start, reserved = busy_port, busy_port + 1
    command = 'source "$1"; free_port "$2" "$3"'
    result = subprocess.run(
        ["bash", "-c", command, "bash", SCRIPT, str(start), str(reserved)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    assert int(result.stdout) > reserved

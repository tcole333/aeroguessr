"""The compose stacks keep the AeroAPI budget in Redis and bound what the host stores.

Two stacks run the game: the maintainer's (infra/, built from source on the Pi) and the
self-hosters' (selfhost/, on the published images). In both, Redis must never evict the
budget counters and must not rewrite an SD card every second, and every container caps its
logs and declares a memory limit.

Locally, every checkout runs its own copies of the maintainer's stack and of the integration
stack, under its own Compose project, so they fix no container names or test ports.
"""

import re
import shlex
from pathlib import Path

import pytest
import yaml

from backend.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
INFRA = REPO_ROOT / "infra"
SELFHOST = REPO_ROOT / "selfhost"


def _services(compose_file: Path) -> dict:
    return yaml.safe_load(compose_file.read_text())["services"]


SERVICES = _services(INFRA / "docker-compose.yml")
PI_COMPOSE = yaml.safe_load((INFRA / "docker-compose.pi.yml").read_text())
PI_SERVICES = PI_COMPOSE["services"]
TEST_SERVICES = _services(INFRA / "docker-compose.test.yml")
SELFHOST_SERVICES = _services(SELFHOST / "compose.yaml")
STACKS = {"maintainer": SERVICES, "selfhost": SELFHOST_SERVICES}
STACK_SERVICES = [(stack, service) for stack, services in STACKS.items() for service in services]


def _redis_option(services: dict, name: str) -> str:
    args = shlex.split(services["redis"]["command"])
    return args[args.index(f"--{name}") + 1]


def _environment(service: dict) -> dict[str, str]:
    return dict(entry.split("=", 1) for entry in service["environment"])


def _env_file_names(path: Path) -> set[str]:
    lines = (line.strip() for line in path.read_text().splitlines())
    return {line.split("=", 1)[0] for line in lines if line and not line.startswith("#")}


# Both stacks


@pytest.mark.parametrize("stack", sorted(STACKS))
def test_redis_never_evicts_keys(stack: str) -> None:
    assert _redis_option(STACKS[stack], "maxmemory-policy") == "noeviction"


@pytest.mark.parametrize("stack", sorted(STACKS))
def test_redis_keeps_no_append_only_file(stack: str) -> None:
    assert _redis_option(STACKS[stack], "appendonly") == "no"


@pytest.mark.parametrize(("stack", "service"), STACK_SERVICES)
def test_service_caps_its_log_files(stack: str, service: str) -> None:
    assert "max-size" in STACKS[stack][service].get("logging", {}).get("options", {})


@pytest.mark.parametrize(("stack", "service"), STACK_SERVICES)
def test_service_has_a_memory_limit(stack: str, service: str) -> None:
    assert "mem_limit" in STACKS[stack][service]


# The maintainer's stack


def test_backend_reads_its_settings_from_the_repo_root_env_file() -> None:
    assert [entry["path"] for entry in SERVICES["backend"]["env_file"]] == ["../.env"]


def test_backend_compose_environment_holds_only_container_wiring() -> None:
    """Setting defaults live in backend/settings.py, not in Compose."""
    assert set(_environment(SERVICES["backend"])) == {"REDIS_URL", "PYTHONUNBUFFERED"}


def test_pi_override_points_the_ingest_at_the_hosts_dump1090() -> None:
    assert PI_SERVICES["backend"]["environment"] == ["ADSB_HOST=host.docker.internal"]


def test_pi_keeps_the_project_and_container_names_its_containers_were_created_under() -> None:
    """Its Redis volume holds the AeroAPI budget counters; another project would start empty."""
    names = {service: config.get("container_name") for service, config in PI_SERVICES.items()}

    assert (PI_COMPOSE["name"], names) == (
        "infra",
        {
            "nginx": "plane-game-nginx",
            "frontend": "plane-game-frontend",
            "backend": "plane-game-backend",
            "redis": "plane-game-redis",
        },
    )


# Local stacks, one Compose project per checkout


def test_local_stacks_take_container_names_from_their_compose_project() -> None:
    """A fixed name would be shared by every checkout's stack."""
    fixed = [
        name
        for services in (SERVICES, TEST_SERVICES)
        for name, service in services.items()
        if "container_name" in service
    ]

    assert fixed == []


def test_integration_stack_publishes_no_host_ports() -> None:
    """It runs next to local Redis and API servers, and other checkouts' integration stacks."""
    assert [name for name, service in TEST_SERVICES.items() if "ports" in service] == []


# The self-hosters' stack


@pytest.mark.parametrize("service", ["backend", "frontend"])
def test_selfhost_runs_the_published_image_at_the_version_from_env(service: str) -> None:
    image = SELFHOST_SERVICES[service]["image"]

    assert image.startswith(f"ghcr.io/tcole333/aeroguessr-{service}:${{AEROGUESSR_VERSION:?")


def test_selfhost_pulls_the_images_the_release_workflow_publishes() -> None:
    workflow = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "release.yml").read_text())
    job = workflow["jobs"]["image"]
    published = {entry["image"] for entry in job["strategy"]["matrix"]["include"]}
    names = next(step for step in job["steps"] if step.get("id") == "meta")["with"]["images"]
    pulled = {
        name: service["image"].split(":")[0]
        for name, service in SELFHOST_SERVICES.items()
        if service["image"].startswith("ghcr.io/")
    }

    assert (names, pulled) == (
        "ghcr.io/${{ github.repository_owner }}/aeroguessr-${{ matrix.image }}",
        {image: f"ghcr.io/tcole333/aeroguessr-{image}" for image in published},
    )


def test_selfhost_builds_nothing() -> None:
    assert [name for name, service in SELFHOST_SERVICES.items() if "build" in service] == []


def test_selfhost_publishes_a_port_only_for_the_frontend() -> None:
    assert [name for name, service in SELFHOST_SERVICES.items() if "ports" in service] == [
        "frontend"
    ]


def test_selfhost_backend_reads_the_env_file_next_to_the_compose_file() -> None:
    assert SELFHOST_SERVICES["backend"]["env_file"] == ".env"


def test_selfhost_backend_reaches_redis_inside_the_stack() -> None:
    assert _environment(SELFHOST_SERVICES["backend"])["REDIS_URL"] == "redis://redis:6379/0"


def test_selfhost_ingest_defaults_to_a_feeder_on_the_docker_host() -> None:
    backend = SELFHOST_SERVICES["backend"]

    assert (
        _environment(backend)["ADSB_HOST"],
        "host.docker.internal:host-gateway" in backend["extra_hosts"],
    ) == ("${ADSB_HOST:-host.docker.internal}", True)


def test_selfhost_env_example_names_only_settings_and_compose_variables() -> None:
    """A misspelt name in the template would be silently ignored by the backend."""
    settings = {name.upper() for name in Settings.model_fields}
    compose_variables = set(re.findall(r"\$\{(\w+)", (SELFHOST / "compose.yaml").read_text()))

    unknown = _env_file_names(SELFHOST / ".env.example") - settings - compose_variables

    assert unknown == set()

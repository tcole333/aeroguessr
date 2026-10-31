"""scripts/auto-update.sh deploys each new commit until a build succeeds, and keeps its log bounded.

Each test runs the real script from a clone of a local bare "origin" repo, with
real git. `docker` and `curl` are stand-ins on PATH that record their arguments
and fail on request, so no Docker daemon or network is needed.
"""

import fcntl
import os
import re
import shutil
import stat
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "auto-update.sh"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_KEEP_BYTES = 1024 * 1024
HAS_FLOCK = shutil.which("flock") is not None
UNPRIVILEGED_ONLY = pytest.mark.skipif(
    os.geteuid() == 0, reason="root ignores the read-only permissions these tests rely on"
)

FAKE_DOCKER = """#!/bin/bash
echo "$*" >> "$FAKE_STATE/docker-calls"
case " $* " in
  *" build "*) [ ! -e "$FAKE_STATE/fail-build" ] ;;
  *" exec "*) cat > /dev/null; [ ! -e "$FAKE_STATE/fail-exec" ] && echo '{"status": "ready"}' ;;
esac
"""

FAKE_CURL = """#!/bin/bash
[ ! -e "$FAKE_STATE/fail-curl" ]
"""

# macOS has no flock(1); the Pi and CI do. Without it the lock is a no-op here
# and the test that needs the real lock is skipped.
FAKE_FLOCK = """#!/bin/bash
exit 0
"""


class Pi:
    """A checkout laid out like /home/pi/plane-game-v4, with its origin and fake tools."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.origin = root / "origin.git"
        self.publisher = root / "publisher"
        self.app = root / "app"
        self.state = root / "state"
        self.bin = root / "bin"
        self.env = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(root),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
            "FAKE_STATE": str(self.state),
            # Fail the readiness gate on the first probe instead of after 60 s.
            "READY_TIMEOUT_SECONDS": "0",
        }

        self.state.mkdir()
        self.bin.mkdir()
        tools = {"docker": FAKE_DOCKER, "curl": FAKE_CURL}
        if not HAS_FLOCK:
            tools["flock"] = FAKE_FLOCK
        for name, body in tools.items():
            tool = self.bin / name
            tool.write_text(body)
            tool.chmod(0o755)

        self._git(root, "init", "--bare", "--initial-branch=main", str(self.origin))
        self._git(root, "clone", str(self.origin), str(self.publisher))
        self.first_commit = self.publish("first")
        self._git(root, "clone", str(self.origin), str(self.app))
        (self.app / "scripts").mkdir()
        shutil.copy(SCRIPT, self.app / "scripts" / "auto-update.sh")
        (self.app / "logs").mkdir()

    def _git(self, cwd: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=cwd, env=self.env, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def publish(self, message: str) -> str:
        """Push a new commit to origin/main and return its sha."""
        self._git(self.publisher, "commit", "--allow-empty", "-m", message)
        self._git(self.publisher, "push", "origin", "HEAD:main")
        return self._git(self.publisher, "rev-parse", "HEAD")

    def rewind(self, sha: str) -> None:
        """Force-push origin/main back to an older commit."""
        self._git(self.publisher, "push", "--force", "origin", f"{sha}:main")

    def head(self) -> str:
        return self._git(self.app, "rev-parse", "HEAD")

    def mark_deployed(self) -> None:
        (self.app / ".deployed-commit").write_text(self.head() + "\n")

    def deployed(self) -> str:
        return (self.app / ".deployed-commit").read_text().strip()

    def fail(self, tool_step: str) -> None:
        (self.state / f"fail-{tool_step}").touch()

    def recover(self, tool_step: str) -> None:
        (self.state / f"fail-{tool_step}").unlink()

    def builds(self) -> int:
        calls = self.state / "docker-calls"
        if not calls.exists():
            return 0
        return sum(1 for line in calls.read_text().splitlines() if line.split()[-1] == "build")

    def run(self) -> subprocess.CompletedProcess[str]:
        """Run the script the way the systemd unit does: stdout and stderr appended to the log."""
        log = self.app / "logs" / "auto-update.log"
        with log.open("a") as out:
            return subprocess.run(
                [str(self.app / "scripts" / "auto-update.sh")],
                cwd=self.app,
                env=self.env,
                stdout=out,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=30,
            )

    def log(self) -> str:
        return (self.app / "logs" / "auto-update.log").read_text(errors="replace")


@pytest.fixture
def pi(tmp_path: Path) -> Iterator[Pi]:
    pi = Pi(tmp_path)
    yield pi
    # Restore write access so tmp_path can be cleaned up.
    for path in (pi.app / "logs", pi.app / "logs" / "auto-update.log"):
        if path.exists():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


# Deploying


def test_first_run_without_a_record_deploys_the_checked_out_commit(pi: Pi) -> None:
    pi.run()

    assert pi.deployed() == pi.first_commit


def test_deployed_commit_is_not_rebuilt(pi: Pi) -> None:
    pi.mark_deployed()

    result = pi.run()

    assert (result.returncode, pi.builds(), "Already up to date" in pi.log()) == (0, 0, True)


def test_failed_build_is_retried_on_the_next_run(pi: Pi) -> None:
    pi.mark_deployed()
    new_commit = pi.publish("second")
    pi.fail("build")
    assert pi.run().returncode != 0

    pi.recover("build")
    assert pi.run().returncode == 0

    assert pi.deployed() == new_commit


def test_retry_rebuilds_the_already_pulled_commit(pi: Pi) -> None:
    pi.mark_deployed()
    pi.publish("second")
    pi.fail("build")
    pi.run()

    pi.recover("build")
    pi.run()

    assert pi.builds() == 2


@pytest.mark.parametrize("failing_check", ["exec", "curl"], ids=["readiness", "nginx"])
def test_failure_after_containers_start_is_reported_but_not_rebuilt(
    pi: Pi, failing_check: str
) -> None:
    pi.mark_deployed()
    pi.publish("second")
    pi.fail(failing_check)
    first = pi.run()

    pi.run()

    assert (first.returncode, pi.builds()) == (1, 1)


def test_repeated_build_failures_back_off(pi: Pi) -> None:
    pi.mark_deployed()
    pi.publish("second")
    pi.fail("build")

    for _ in range(3):
        pi.run()

    assert pi.builds() == 2


def test_backoff_is_reported_in_the_log(pi: Pi) -> None:
    pi.mark_deployed()
    pi.publish("second")
    pi.fail("build")

    for _ in range(3):
        pi.run()

    assert "failed to deploy 2 times; next attempt in" in pi.log()


def test_new_commit_is_deployed_without_waiting_out_the_backoff(pi: Pi) -> None:
    pi.mark_deployed()
    pi.publish("second")
    pi.fail("build")
    pi.run()
    pi.run()

    fixed = pi.publish("third")
    pi.recover("build")
    pi.run()

    assert pi.deployed() == fixed


def test_rewound_main_is_reported_instead_of_built(pi: Pi) -> None:
    pi.publish("second")
    pi.run()
    pi.rewind(pi.first_commit)

    result = pi.run()

    assert (result.returncode, pi.builds(), "Cannot fast-forward" in pi.log()) == (1, 1, True)


@pytest.mark.skipif(not HAS_FLOCK, reason="needs flock(1), which the Pi and CI have")
def test_run_is_skipped_while_another_run_holds_the_lock(pi: Pi) -> None:
    with (pi.app / ".auto-update.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

        pi.run()

    assert (pi.builds(), "Another run is still deploying" in pi.log()) == (0, True)


# Log size


FULL_LINE = re.compile(r"line (\d{7}) x{40}")


def _fill_log(pi: Pi, size: int) -> None:
    lines = (f"line {n:07d} {'x' * 40}\n" for n in range(size // 53 + 2))
    (pi.app / "logs" / "auto-update.log").write_text("".join(lines))


@UNPRIVILEGED_ONLY
def test_oversized_log_is_trimmed_in_a_read_only_directory(pi: Pi) -> None:
    pi.mark_deployed()
    _fill_log(pi, LOG_MAX_BYTES + 1)
    (pi.app / "logs").chmod(0o555)

    pi.run()

    assert len(pi.log().encode()) < LOG_KEEP_BYTES + 4096


def test_trimmed_log_starts_with_a_whole_recent_line(pi: Pi) -> None:
    pi.mark_deployed()
    _fill_log(pi, LOG_MAX_BYTES + 1)

    pi.run()

    first_line = FULL_LINE.fullmatch(pi.log().split("\n", 1)[0])
    assert first_line and int(first_line[1]) > 0


def test_trim_is_reported_in_the_log(pi: Pi) -> None:
    pi.mark_deployed()
    _fill_log(pi, LOG_MAX_BYTES + 1)

    pi.run()

    assert "Trimmed logs/auto-update.log" in pi.log()


def test_log_without_line_breaks_keeps_its_newest_bytes(pi: Pi) -> None:
    pi.mark_deployed()
    (pi.app / "logs" / "auto-update.log").write_text("x" * (LOG_MAX_BYTES + 1))

    pi.run()

    assert LOG_KEEP_BYTES <= len(pi.log().encode()) < LOG_KEEP_BYTES + 4096


@UNPRIVILEGED_ONLY
def test_failed_trim_is_reported_as_a_failure(pi: Pi) -> None:
    pi.mark_deployed()
    _fill_log(pi, LOG_MAX_BYTES + 1)
    log = pi.app / "logs" / "auto-update.log"
    log.chmod(0o444)

    result = subprocess.run(
        [str(pi.app / "scripts" / "auto-update.sh")],
        cwd=pi.app,
        env=pi.env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert ("Could not rotate" in result.stdout, "Trimmed" in result.stdout) == (True, False)

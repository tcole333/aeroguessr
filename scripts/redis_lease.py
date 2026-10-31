"""Lease a database on the shared test Redis, so parallel sessions never use the same one.

Until #195 moves the tests to testcontainers, sessions on one machine share a test Redis
(127.0.0.1:6381 on the maintainer's Mac), and each run needs a database of its own. A lease is
the key lease:db:N in db 0, holding its owner's name, set with NX and a 2-hour expiry. Only an
empty database can be leased, so a lease never takes, or later flushes, data it didn't write.

    uv run python scripts/redis_lease.py lease     # prints redis://127.0.0.1:6381/N
    uv run python scripts/redis_lease.py release   # flushes the database, ends the lease
    uv run python scripts/redis_lease.py list

The owner defaults to the checkout's name (scripts/checkout-env.sh project), and leasing again
under the same owner renews the lease. A second run in the same checkout at the same time, such
as a subagent's, needs its own owner (--owner). TEST_REDIS_SERVER names another server.

Leasing marks the server as a shared test Redis for 30 days. `lease --if-shared`, which
scripts/worktree-setup.sh runs, leases only from a marked server or from TEST_REDIS_SERVER, so
setting up a checkout never writes to some other Redis that happens to listen on the port.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

import redis

LEASE_SECONDS = 2 * 60 * 60
MARKER_KEY = "lease:shared-test-redis"
MARKER_SECONDS = 30 * 24 * 60 * 60
DEFAULT_SERVER = "redis://127.0.0.1:6381"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Both act only while ARGV[1] still holds the lease, so an expired lease that someone else
# has taken since is left alone.
EXTEND_IF_HELD = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
DELETE_IF_HELD = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

EXIT_NO_FREE_DATABASE = 1
EXIT_REDIS_ERROR = 2
EXIT_NOT_SHARED = 3
EXIT_OTHER_ERROR = 4


class LeaseError(Exception):
    pass


class Server:
    """A Redis server whose db 0 holds the leases and whose other databases are leased."""

    def __init__(self, url: str) -> None:
        self.base = urlsplit(url)._replace(path="", query="").geturl()
        self.registry = self.client(0)

    def client(self, db: int) -> redis.Redis:
        return redis.Redis.from_url(
            f"{self.base}/{db}", decode_responses=True, socket_connect_timeout=2
        )

    def url(self, db: int) -> str:
        return f"{self.base}/{db}"

    def databases(self) -> list[int]:
        try:
            count = int(self.registry.config_get("databases")["databases"])
        except redis.ResponseError:  # CONFIG is disabled on this server
            count = 16
        return list(range(1, count))


def lease_key(db: int) -> str:
    return f"lease:db:{db}"


def holders(server: Server, databases: list[int] | None) -> list[tuple[int, str | None]]:
    """Each database (all leasable ones by default) with the owner holding it, if any."""
    dbs = databases or server.databases()
    return list(zip(dbs, server.registry.mget([lease_key(db) for db in dbs]), strict=True))


def lease(server: Server, owner: str, databases: list[int] | None = None) -> int:
    """Renew owner's lease, or lease the first empty database; return its number."""
    held = holders(server, databases)
    for db, holder in held:
        if holder == owner and server.registry.eval(
            EXTEND_IF_HELD, 1, lease_key(db), owner, LEASE_SECONDS
        ):
            return db
    for db, holder in held:
        # A database with keys may belong to anyone, leased or not: never take it.
        if holder is None and server.client(db).dbsize() == 0:
            if server.registry.set(lease_key(db), owner, nx=True, ex=LEASE_SECONDS):
                return db
    raise LeaseError(f"No free database on {server.base}. Holders:\n" + "\n".join(report(server)))


def release(server: Server, owner: str, databases: list[int] | None = None) -> int | None:
    """Flush owner's database and end the lease; return its number, or None if owner had none."""
    for db, holder in holders(server, databases):
        # Renewing first means the lease can't expire and pass to someone else mid-flush.
        if holder != owner or not server.registry.eval(
            EXTEND_IF_HELD, 1, lease_key(db), owner, LEASE_SECONDS
        ):
            continue
        server.client(db).flushdb()
        server.registry.eval(DELETE_IF_HELD, 1, lease_key(db), owner)
        return db
    return None


def report(server: Server) -> list[str]:
    lines = []
    for db in server.databases():
        holder = server.registry.get(lease_key(db))
        keys = server.client(db).dbsize()
        if holder:
            minutes = max(server.registry.ttl(lease_key(db)), 0) // 60
            lines.append(f"db {db}: {holder}, {minutes} min left, {keys} keys")
        elif keys:
            lines.append(f"db {db}: no lease, {keys} keys (not leasable until it's empty)")
    return lines


def checkout_owner() -> str:
    script = REPO_ROOT / "scripts" / "checkout-env.sh"
    return subprocess.run(  # noqa: S603 (the repo's own script, with fixed arguments)
        [str(script), "project"], capture_output=True, text=True, check=True
    ).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["lease", "release", "list"])
    parser.add_argument("--owner", help="who holds the lease (default: this checkout's name)")
    parser.add_argument(
        "--server", help=f"Redis URL (default: TEST_REDIS_SERVER, else {DEFAULT_SERVER})"
    )
    parser.add_argument(
        "--if-shared",
        action="store_true",
        help="lease only from a server marked as shared, or named by --server/TEST_REDIS_SERVER",
    )
    args = parser.parse_args()
    named = args.server or os.environ.get("TEST_REDIS_SERVER")
    server = Server(named or DEFAULT_SERVER)
    try:
        if args.command == "lease":
            if args.if_shared and not named and not server.registry.exists(MARKER_KEY):
                print(
                    f"{server.base} isn't marked as a shared test Redis; to use it, run"
                    " uv run python scripts/redis_lease.py lease",
                    file=sys.stderr,
                )
                return EXIT_NOT_SHARED
            owner = args.owner or checkout_owner()
            if not args.if_shared:
                server.registry.set(MARKER_KEY, "scripts/redis_lease.py", ex=MARKER_SECONDS)
            db = lease(server, owner)
            print(server.url(db))
            print(f"{owner} holds db {db} for 2 hours; leasing again renews it.", file=sys.stderr)
        elif args.command == "release":
            owner = args.owner or checkout_owner()
            db = release(server, owner)
            message = f"Flushed and released db {db}." if db else f"{owner} holds no lease."
            print(message, file=sys.stderr)
        else:
            print("\n".join(report(server)) or "No leases, and no other database holds keys.")
    except LeaseError as error:
        print(error, file=sys.stderr)
        return EXIT_NO_FREE_DATABASE
    except (redis.RedisError, OSError) as error:
        print(f"Can't use the test Redis at {server.base}: {error}", file=sys.stderr)
        return EXIT_REDIS_ERROR
    except subprocess.CalledProcessError as error:
        print(f"scripts/checkout-env.sh couldn't name the owner: {error.stderr}", file=sys.stderr)
        return EXIT_OTHER_ERROR
    return 0


if __name__ == "__main__":
    sys.exit(main())

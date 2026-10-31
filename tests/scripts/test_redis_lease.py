"""scripts/redis_lease.py gives a test database to one owner at a time and flushes it on release.

The tests run on the server TEST_REDIS_URL names. They lease an empty database the way sessions
do, under owner names no session uses, and write only to it and to the database TEST_REDIS_URL
names.
"""

import importlib.util
import os
import uuid
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.integration

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "redis_lease.py"


def load_leases() -> ModuleType:
    spec = importlib.util.spec_from_file_location("redis_lease", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configured_test_redis_url() -> str:
    url = os.environ.get("TEST_REDIS_URL")
    if not url:
        pytest.fail("TEST_REDIS_URL is not set; see tests/README.md.", pytrace=False)
    return url


def test_a_database_has_one_owner_until_released_flushed() -> None:
    leases = load_leases()
    server = leases.Server(configured_test_redis_url())
    first, second = f"test-{uuid.uuid4()}", f"test-{uuid.uuid4()}"
    db = leases.lease(server, first)
    try:
        server.client(db).set("left:by:a:run", "1", ex=60)
        with pytest.raises(leases.LeaseError):
            leases.lease(server, second, databases=[db])

        renewed = leases.lease(server, first)
        released = leases.release(server, first)

        assert (renewed, released, server.client(db).dbsize()) == (db, db, 0)
        assert leases.lease(server, second, databases=[db]) == db
    finally:
        leases.release(server, first, databases=[db])
        leases.release(server, second, databases=[db])


def test_a_database_holding_keys_is_never_leased() -> None:
    url = configured_test_redis_url()
    leases = load_leases()
    server = leases.Server(url)
    db = int(url.rsplit("/", 1)[1])
    data = server.client(db)
    data.set("someone:else", "1", ex=60)
    try:
        with pytest.raises(leases.LeaseError):
            leases.lease(server, f"test-{uuid.uuid4()}", databases=[db])

        assert data.get("someone:else") == "1"
    finally:
        data.delete("someone:else")

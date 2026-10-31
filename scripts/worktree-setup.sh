#!/bin/bash
# Make a fresh checkout, usually a git worktree, ready for the unit suite and `make demo`, then
# print the Compose projects, container and ports its stacks use. Running it again is quick.
#
#   - Python: this checkout's own .venv, synced from uv.lock by `uv sync` out of uv's cache, on
#     the Python 3.12 that .python-version pins.
#   - frontend/node_modules: a clone of one shared copy per package-lock.json, kept in
#     ~/.cache/aeroguessr/node_modules. The first checkout with a new lockfile runs npm ci,
#     and its result becomes the shared copy. On APFS a clone takes no disk space until it
#     changes, and every checkout's copy is its own: npm install or Vite's cache in one
#     checkout never changes another's.
#   - A database on the test Redis that sessions on this machine share, leased to this
#     checkout for 2 hours (scripts/redis_lease.py), if a lease has marked that Redis as shared.

set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck source=scripts/checkout-env.sh
source scripts/checkout-env.sh

NODE_STORE=${XDG_CACHE_HOME:-$HOME/.cache}/aeroguessr/node_modules
# How many lockfiles' copies the store keeps. Checkouts hold clones, not links, so removing
# a copy never breaks one.
NODE_STORE_KEEP=3

setup_python() {
    uv sync
}

sha256() {
    if command -v sha256sum >/dev/null; then sha256sum; else shasum -a 256; fi
}

# Print a key for what npm ci installs here: the lockfile, plus Node's major version and the
# platform and architecture it runs on, which pick the native binaries some packages ship.
node_modules_key() {
    {
        cat frontend/package-lock.json
        node -p '[process.versions.node.split(".")[0], process.platform, process.arch].join(" ")'
    } | sha256 | cut -c1-16
}

# Copy directory $1 to $2, as a clone where the filesystem supports it.
clone_dir() {
    if [ "$(uname -s)" = Darwin ]; then
        cp -c -R "$1" "$2"
    else
        cp -R --reflink=auto "$1" "$2"
    fi
}

prune_node_store() {
    local old
    # shellcheck disable=SC2012 # entries have hex names; newest first
    ls -1t "$NODE_STORE" | tail -n +$((NODE_STORE_KEEP + 1)) | while read -r old; do
        rm -rf "${NODE_STORE:?}/$old"
    done
    # Left by runs that stopped while copying, or that lost a race to store the same lockfile.
    find "$NODE_STORE" -maxdepth 2 -name '.partial.*' -mtime +0 -prune -exec rm -rf {} +
}

setup_node_modules() {
    local key entry partial
    key=$(node_modules_key)
    entry=$NODE_STORE/$key
    if [ "$(cat frontend/node_modules/.store-key 2>/dev/null)" = "$key" ]; then
        echo "frontend/node_modules already matches package-lock.json."
        return
    fi
    rm -rf frontend/node_modules
    if [ -d "$entry/node_modules" ]; then
        echo "Cloning frontend/node_modules from $entry"
        # Newest first, so another checkout's prune keeps it while it's being cloned.
        touch "$entry"
        clone_dir "$entry/node_modules" frontend/node_modules
    else
        echo "No shared copy for this package-lock.json yet, so running npm ci."
        (cd frontend && npm ci --prefer-offline --no-audit --no-fund)
        mkdir -p "$NODE_STORE"
        partial=$(mktemp -d "$NODE_STORE/.partial.XXXXXX")
        clone_dir frontend/node_modules "$partial/node_modules"
        # Another checkout's setup may have stored this lockfile meanwhile; keep the first.
        if [ -e "$entry" ]; then rm -rf "$partial"; else mv "$partial" "$entry"; fi
        prune_node_store
    fi
    echo "$key" > frontend/node_modules/.store-key
}

# Lease this checkout a database on the shared test Redis, if a lease has marked one as shared
# (or TEST_REDIS_SERVER names one). Sets TEST_REDIS to its URL, or LEASE_NOTE to why not.
lease_test_redis() {
    local output
    TEST_REDIS=
    if output=$(uv run python scripts/redis_lease.py lease --if-shared 2>&1); then
        TEST_REDIS=$(printf '%s\n' "$output" | grep -m 1 '^redis' || true)
    fi
    LEASE_NOTE=$(printf '%s\n' "$output" | grep -v '^redis' | head -n 1)
}

summary() {
    local project reserved api web redis
    project=$(checkout_project)
    reserved=$(container_ports)
    # shellcheck disable=SC2086 # one port per word
    api=$(free_port 8000 $reserved) || api=none
    # shellcheck disable=SC2086
    web=$(free_port 5173 $reserved) || web=none
    redis=$(docker container inspect \
        --format '{{(index (index .HostConfig.PortBindings "6379/tcp") 0).HostPort}}' \
        "$project-dev-redis" 2>/dev/null) || redis=
    cat <<EOF

Ready. This checkout's stacks are its own:
  make start, make stop   Compose project $project
  make integration-test   Compose project ${project}_test, publishing no ports
  make demo, make dev     Redis container $project-dev-redis, on ${redis:-a free port the first run picks}
                          API and web ports picked as it starts (free now: API $api, web $web)
EOF
    if [ -n "$TEST_REDIS" ]; then
        echo "  Shared test Redis       TEST_REDIS_URL=$TEST_REDIS, leased to $project for 2 h;"
        echo "                          lease again before each run to renew it (tests/README.md 3.2)"
    else
        echo "  Shared test Redis       no lease: $LEASE_NOTE"
    fi
    echo
    echo 'Unit suite: uv run pytest -m "not integration" tests/'
}

for tool in uv node npm; do
    if ! command -v "$tool" >/dev/null; then
        echo "worktree-setup.sh needs $tool; see the README." >&2
        exit 1
    fi
done

setup_python
setup_node_modules
lease_test_redis
summary

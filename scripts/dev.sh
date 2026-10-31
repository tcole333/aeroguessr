#!/bin/bash
# Run the game locally: Redis, the API, the ingest and Vite, in one terminal.
# Ctrl-C, SIGINT, SIGTERM or SIGHUP stops everything except Redis, which keeps its container for
# the next run, and returns once the processes are gone and their ports are free.
#
#   scripts/dev.sh demo   synthetic planes, AeroAPI off whatever .env says (make demo)
#   scripts/dev.sh live   settings from .env as they are (make dev)
#
# Each checkout has its own Redis container, and every port is picked free, so stacks from
# parallel worktrees run side by side. DEV_API_PORT, DEV_WEB_PORT and DEV_REDIS_PORT pick
# ports instead. NETWORK=1 makes the API reachable from phones on the LAN and points the
# WebSocket URL at this machine.

set -euo pipefail

# Started with & from a non-interactive shell, as agents start it, this script inherits SIGINT
# ignored, and bash can't trap a signal that was ignored when it started. Run it again with SIGINT
# back at its default, so the INT trap below works.
if [ -z "${DEV_SH_SIGINT_RESET:-}" ] && command -v python3 >/dev/null; then
    export DEV_SH_SIGINT_RESET=1
    exec python3 -c 'import os, signal, sys
signal.signal(signal.SIGINT, signal.SIG_DFL)
os.execv(sys.argv[1], sys.argv[1:])' "$0" "$@"
fi

cd "$(dirname "$0")/.."
# shellcheck source=scripts/checkout-env.sh
source scripts/checkout-env.sh

MODE=${1:-demo}
REDIS_CONTAINER=$(checkout_project)-dev-redis
API_HOST=127.0.0.1

case "$MODE" in
    demo | live) ;;
    *)
        echo "usage: scripts/dev.sh [demo|live]" >&2
        exit 2
        ;;
esac

# Print this machine's private LAN address, if it has one.
lan_ip() {
    ifconfig 2>/dev/null | awk '/inet (192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)/ {print $2; exit}' \
        || true
}

# Print the port $1 names ($2 is its value), which must be free, or the first free port
# from $3 when it is unset.
choose_port() {
    local name=$1 wanted=$2 start=$3
    if [ -z "$wanted" ]; then
        # shellcheck disable=SC2086 # one port per word
        free_port "$start" $RESERVED_PORTS
        return
    fi
    if ! port_is_free "$wanted"; then
        echo "$name=$wanted, but something already listens on port $wanted." >&2
        return 1
    fi
    echo "$wanted"
}

# This checkout's Redis. The first run creates its container; later runs reuse it, with
# its port and its data, the AeroAPI budget counters among them.
start_redis() {
    local published
    published=$(docker container inspect \
        --format '{{(index (index .HostConfig.PortBindings "6379/tcp") 0).HostPort}}' \
        "$REDIS_CONTAINER" 2>/dev/null) || published=
    if [ -z "$published" ]; then
        REDIS_PORT=$(choose_port DEV_REDIS_PORT "${DEV_REDIS_PORT:-}" 6379)
        if ! docker run -d --name "$REDIS_CONTAINER" -p "127.0.0.1:$REDIS_PORT:6379" redis:7-alpine >/dev/null; then
            echo "Could not start Redis on port $REDIS_PORT." >&2
            exit 1
        fi
        return
    fi
    if [ -n "${DEV_REDIS_PORT:-}" ] && [ "$published" != "$DEV_REDIS_PORT" ]; then
        echo "$REDIS_CONTAINER publishes port $published, not $DEV_REDIS_PORT." >&2
        echo "Remove it (docker rm -fv $REDIS_CONTAINER) or unset DEV_REDIS_PORT." >&2
        exit 1
    fi
    REDIS_PORT=$published
    if ! docker start "$REDIS_CONTAINER" >/dev/null; then
        echo "Could not start $REDIS_CONTAINER on port $REDIS_PORT. If something else holds the" >&2
        echo "port now, remove the container (docker rm -fv $REDIS_CONTAINER) to get a new one." >&2
        exit 1
    fi
}

# Start a process in the background, in its own process group, with its output prefixed by name.
PIDS=()
run() {
    local name=$1
    shift
    ("$@" 2>&1 | awk -v prefix="[$name] " '{ print prefix $0; fflush() }') &
    PIDS+=("$!")
}

# Stop every process group this script started, then wait until they're gone, so their ports are
# free when it exits. Whatever is still running after 5 s is killed.
stop_all() {
    trap - EXIT INT TERM HUP
    local pid _ running
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do
        kill -- "-$pid" 2>/dev/null || true
    done
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        running=false
        for pid in ${PIDS[@]+"${PIDS[@]}"}; do
            if kill -0 -- "-$pid" 2>/dev/null; then
                running=true
            fi
        done
        $running || return 0
        sleep 0.5
    done
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do
        kill -KILL -- "-$pid" 2>/dev/null || true
    done
}

# Ports that stopped containers will want back, which no new listener may take.
RESERVED_PORTS=$(container_ports)
start_redis
export REDIS_URL="redis://127.0.0.1:$REDIS_PORT/0"

API_PORT=$(choose_port DEV_API_PORT "${DEV_API_PORT:-}" 8000)
WEB_PORT=$(choose_port DEV_WEB_PORT "${DEV_WEB_PORT:-}" 5173)
# Vite listens on DEV_WEB_PORT and proxies /api to DEV_API_PORT (frontend/vite.config.ts).
export DEV_API_PORT=$API_PORT DEV_WEB_PORT=$WEB_PORT

if [ "$MODE" = demo ]; then
    # The ingest serves its synthetic feed on ADSB_PORT and reads it back. If another stack's
    # feed held that port, this ingest would read that stack's planes instead.
    # shellcheck disable=SC2086 # one port per word
    ADSB_PORT=$(free_port 30003 $RESERVED_PORTS)
    export ADSB_PORT FAKE_ADSB=1 FAKE_ADSB_FILE=synthetic FLIGHTAWARE_API_KEY=
fi

if [ "${NETWORK:-0}" = 1 ]; then
    ip=$(lan_ip)
    if [ -z "$ip" ]; then
        echo "NETWORK=1: no private LAN address found." >&2
        exit 1
    fi
    API_HOST=0.0.0.0
    export WS_BASE_URL="ws://$ip:$API_PORT/"
    echo "On your phone, open http://$ip:$WEB_PORT"
fi

# Job control gives each process its own group, so stopping one stops its children too
# (uvicorn's reloader, npm's node). Ctrl-C, or any process exiting, stops them all.
set -m
trap 'stop_all; exit 130' INT TERM HUP
trap stop_all EXIT

run api uv run uvicorn backend.app:app --reload --host "$API_HOST" --port "$API_PORT"
run ingest uv run python -m backend.ingest.main
run web npm --prefix frontend run dev

echo "Running in $MODE mode. Ctrl-C stops."
echo "  Game:  http://localhost:$WEB_PORT"
echo "  API:   http://127.0.0.1:$API_PORT (docs at /api/v0/docs)"
echo "  Redis: 127.0.0.1:$REDIS_PORT, container $REDIS_CONTAINER (kept after Ctrl-C)"
while :; do
    for pid in ${PIDS[@]+"${PIDS[@]}"}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "A process exited; stopping the rest." >&2
            exit 1
        fi
    done
    sleep 1
done

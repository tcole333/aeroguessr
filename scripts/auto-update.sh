#!/bin/bash
# Auto-update script - polls GitHub and rebuilds on changes
# Deployed to Pi at /home/pi/plane-game-v4/scripts/auto-update.sh
# Run by systemd timer every 1 minute
#
# The fast-forward below replaces this file while it runs. Everything runs from
# main(), which bash parses in full before the call on the last line, so a run
# finishes with the code it started with; the next run picks up the new code.

set -e

# The repo root, which is the parent of scripts/.
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f infra/docker-compose.yml -f infra/docker-compose.pi.yml)
READY_TIMEOUT_SECONDS=${READY_TIMEOUT_SECONDS:-60}
READY_POLL_SECONDS=5
LOG_FILE=logs/auto-update.log
LOG_MAX_BYTES=$((5 * 1024 * 1024))
LOG_KEEP_BYTES=$((1024 * 1024))
# The commit whose images were last built and started. It is written only after
# `up -d` succeeds, so a failed build or start is retried even though the
# checkout already moved HEAD.
DEPLOYED_FILE=.deployed-commit
# "<sha> <attempts> <epoch of the last attempt>" while a commit fails to deploy.
ATTEMPTS_FILE=.deploy-attempts
# Seconds to wait, from the start of a commit's Nth attempt, before the next:
# the first retry is immediate, then 1, 3, 7, 15 and 31 minutes, then hourly.
RETRY_WAITS=(0 0 60 180 420 900 1860 3600)
# Held for the whole run, so a manual run during a timer run's build does not
# start a second build next to it.
LOCK_FILE=.auto-update.lock

# Print the backend's /readyz body; succeed only when it reports ready.
# Probes from inside the backend container so the gate does not depend on nginx
# having picked up config changes: nginx.conf is a single-file bind mount, and
# `up -d` does not recreate nginx when only that file changes.
backend_readiness() {
    "${COMPOSE[@]}" exec -T backend python3 - <<'PY'
import sys
import urllib.error
import urllib.request

try:
    with urllib.request.urlopen("http://localhost:8000/readyz", timeout=5) as resp:
        print(resp.read().decode())
except urllib.error.HTTPError as err:
    print(err.read().decode())
    sys.exit(1)
except OSError as err:
    print(f"readiness probe failed: {err}")
    sys.exit(1)
PY
}

# Once the log passes LOG_MAX_BYTES, keep only its newest LOG_KEEP_BYTES. It
# trims in place because logs/ is also a bind mount for the containers: Docker
# creates it as root, so this user can write the file but cannot rename or
# create entries next to it. The service opens the log for appending, so its
# handle keeps writing at the new end.
# Called from a `||` list, where set -e is off, so every step checks its own
# result.
rotate_log() {
    [ -f "$LOG_FILE" ] || return 0
    local size kept trimmed=1
    size=$(wc -c < "$LOG_FILE") || return 1
    [ "$size" -gt "$LOG_MAX_BYTES" ] || return 0
    kept=$(mktemp) || return 1
    trim_log_through "$kept" && trimmed=0
    rm -f "$kept"
    [ "$trimmed" -eq 0 ] || return 1
    echo "$(date): Trimmed $LOG_FILE from $((size)) to about $LOG_KEEP_BYTES bytes"
}

# Copy the newest LOG_KEEP_BYTES of the log to $1 and write them back, dropping
# the cut-off first line unless it is the only line.
trim_log_through() {
    local first_line=1
    tail -c "$LOG_KEEP_BYTES" "$LOG_FILE" > "$1" || return 1
    [ "$(wc -l < "$1")" -le 1 ] || first_line=2
    tail -n +"$first_line" "$1" > "$LOG_FILE"
}

# Exit quietly while a commit that keeps failing waits out RETRY_WAITS, so a
# build that only fails on the Pi does not run every minute. A new commit
# starts over. Otherwise record this attempt before building, so a run that
# dies mid-build still counts.
wait_out_retry_backoff() {
    local sha="" attempts="" last="" wait now
    now=$(date +%s)
    read -r sha attempts last 2>/dev/null < "$ATTEMPTS_FILE" || true
    case "$attempts" in '' | *[!0-9]*) sha="" ;; esac
    case "$last" in '' | *[!0-9]*) sha="" ;; esac
    if [ "$sha" = "$REMOTE" ]; then
        wait=${RETRY_WAITS[$((attempts < 7 ? attempts : 7))]}
        if [ $((now - last)) -lt "$wait" ]; then
            echo "$(date): $REMOTE failed to deploy $attempts times; next attempt in $((last + wait - now))s"
            exit 0
        fi
    else
        attempts=0
    fi
    echo "$REMOTE $((attempts + 1)) $now" > "$ATTEMPTS_FILE"
}

main() {
    exec 9> "$LOCK_FILE"
    if ! flock -n 9; then
        echo "$(date): Another run is still deploying, skipping"
        exit 0
    fi

    rotate_log || echo "$(date): Could not rotate $LOG_FILE"

    git fetch origin main
    REMOTE=$(git rev-parse origin/main)
    DEPLOYED=$(cat "$DEPLOYED_FILE" 2>/dev/null || true)

    if [ "$DEPLOYED" = "$REMOTE" ]; then
        echo "$(date): Already up to date"
        exit 0
    fi

    wait_out_retry_backoff

    if [ "$(git rev-parse HEAD)" = "$REMOTE" ]; then
        echo "$(date): $REMOTE is checked out but not deployed, building..."
    else
        echo "$(date): New commits detected, updating..."
        # Fast-forward only: if main was rewound or the checkout has local
        # commits, stop here instead of building something that is not main.
        git merge --ff-only "$REMOTE"
        if [ "$(git rev-parse HEAD)" != "$REMOTE" ]; then
            echo "$(date): Cannot fast-forward $(git rev-parse HEAD) to $REMOTE; fix the checkout by hand"
            exit 1
        fi
    fi

    # Rebuild and restart
    "${COMPOSE[@]}" build
    "${COMPOSE[@]}" up -d
    # The new images are running. A readiness failure below is reported but
    # not retried: rebuilding the same commit would not fix it.
    echo "$REMOTE" > "$DEPLOYED_FILE"
    rm -f "$ATTEMPTS_FILE"

    # Deploy gate. `up -d` has already waited for backend liveness (/healthz), so
    # this waits for ingest to connect to its feed and heartbeat (/readyz).
    deadline=$((SECONDS + READY_TIMEOUT_SECONDS))
    until readiness=$(backend_readiness 2>&1); do
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "$(date): Backend not ready after ${READY_TIMEOUT_SECONDS}s: $readiness"
            exit 1
        fi
        sleep "$READY_POLL_SECONDS"
    done
    echo "$(date): Backend ready: $readiness"

    # Players reach the backend through nginx; check that path too.
    if curl -sf --max-time 5 http://localhost/healthz > /dev/null; then
        echo "$(date): Deploy successful!"
    else
        echo "$(date): nginx is not serving the backend (/healthz)!"
        exit 1
    fi

    # Each rebuild leaves the previous images dangling. Prune only those: the
    # build cache holds the npm and uv cache mounts that keep the next
    # dependency change fast.
    docker image prune -f || echo "$(date): docker image prune failed"
}

main "$@"; exit

#!/bin/bash
# Names and ports that keep this checkout's local stacks apart from every other checkout's,
# so parallel git worktrees never share containers, volumes or ports.
#
# scripts/dev.sh and scripts/worktree-setup.sh source this file. The Makefile runs
# `scripts/checkout-env.sh project`.

# CDPATH would make cd print the directory into the captured output.
CHECKOUT_ROOT=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)

# Print this checkout's Compose project name: COMPOSE_PROJECT_NAME if set, else "aeroguessr-"
# and the checkout directory's name. Its stacks and containers add a suffix (_test, -dev-redis).
checkout_project() {
    if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
        echo "$COMPOSE_PROJECT_NAME"
        return
    fi
    local dir
    dir=$(basename "$CHECKOUT_ROOT" | tr '[:upper:]' '[:lower:]')
    # Compose allows lowercase letters, digits, dashes and underscores. Underscores become dashes
    # too, so no checkout's project can be another checkout's integration project (<name>_test).
    printf 'aeroguessr-%s\n' "$(printf '%s' "$dir" | tr -c 'a-z0-9-' '-')"
}

# Succeed when nothing accepts connections on port $1 at 127.0.0.1 or ::1.
port_is_free() {
    local host
    for host in 127.0.0.1 ::1; do
        if (exec 3<>"/dev/tcp/$host/$1") 2>/dev/null; then
            return 1
        fi
    done
}

# Print the first free port of the 100 from $1, skipping the reserved ports given after it.
free_port() {
    local start=$1 port=$1
    shift
    local reserved=" $* "
    while [ "$port" -lt $((start + 100)) ]; do
        case "$reserved" in
            *" $port "*) ;;
            *)
                if port_is_free "$port"; then
                    echo "$port"
                    return
                fi
                ;;
        esac
        port=$((port + 1))
    done
    echo "No free port in $start-$((start + 99))." >&2
    return 1
}

# Print the host ports that existing containers publish, running or stopped. A stopped
# container gets its port back when it starts again, so a new stack must not take it.
container_ports() {
    local ids
    ids=$(docker ps -aq 2>/dev/null) || return 0
    [ -n "$ids" ] || return 0
    # shellcheck disable=SC2086 # one container id per word
    docker inspect --format '{{range .HostConfig.PortBindings}}{{range .}}{{.HostPort}} {{end}}{{end}}' \
        $ids 2>/dev/null || true
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    case "${1:-}" in
        project) checkout_project ;;
        *)
            echo "usage: scripts/checkout-env.sh project" >&2
            exit 2
            ;;
    esac
fi

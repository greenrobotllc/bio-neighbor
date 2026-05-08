#!/bin/bash
# Stop any running bio-neighbor Python backend on 127.0.0.1:5000.
#
# Pairs with `start_server.sh`. Useful when the macOS app's auto-start
# is hanging onto a stale process from before a code update — symptom
# is HTTP 404 on newly-added endpoints because the running process
# doesn't have the new routes registered.
#
# Idempotent: silent no-op when nothing is running.

set -u

PORT=5000
# Match the exact command the macOS app and start_server.sh launch with
# so we don't accidentally kill an unrelated python process.
PATTERN='backend/api.py'

# Snapshot the set of PIDs to target ONCE up front. We must not re-run
# pgrep later — if a fresh backend is started during the 5-second wait
# (e.g. the user runs start_server.sh in another terminal), re-querying
# would let us SIGKILL processes we never owned.
INITIAL_PIDS=$(pgrep -f "$PATTERN" 2>/dev/null)

if [ -z "$INITIAL_PIDS" ]; then
    echo "No bio-neighbor backend processes found."
    exit 0
fi

for pid in $INITIAL_PIDS; do
    cmd=$(ps -o command= -p "$pid" 2>/dev/null)
    echo "Stopping bio-neighbor backend pid=$pid ($cmd)"
    kill "$pid" 2>/dev/null || true
done

# Wait up to 5s for graceful shutdown, checking only the PIDs we targeted.
for _ in 1 2 3 4 5; do
    sleep 1
    still_alive=""
    for pid in $INITIAL_PIDS; do
        if kill -0 "$pid" 2>/dev/null; then
            still_alive="$still_alive $pid"
        fi
    done
    if [ -z "$still_alive" ]; then
        echo "Backend stopped cleanly."
        exit 0
    fi
done

# SIGKILL only the originally-captured PIDs that are still alive — never
# any newly-spawned process matching the same pattern.
echo "Some processes did not exit on SIGTERM, sending SIGKILL..."
for pid in $INITIAL_PIDS; do
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi
done
echo "Done."

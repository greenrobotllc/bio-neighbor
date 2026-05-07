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

found_any=0
for pid in $(pgrep -f "$PATTERN" 2>/dev/null); do
    found_any=1
    cmd=$(ps -o command= -p "$pid" 2>/dev/null)
    echo "Stopping bio-neighbor backend pid=$pid ($cmd)"
    kill "$pid" 2>/dev/null || true
done

if [ "$found_any" -eq 0 ]; then
    echo "No bio-neighbor backend processes found."
    exit 0
fi

# Wait up to 5s for graceful shutdown, then SIGKILL anything still alive.
for _ in 1 2 3 4 5; do
    sleep 1
    remaining=$(pgrep -f "$PATTERN" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$remaining" = "0" ]; then
        echo "Backend stopped cleanly."
        exit 0
    fi
done

echo "Some processes did not exit on SIGTERM, sending SIGKILL..."
for pid in $(pgrep -f "$PATTERN" 2>/dev/null); do
    kill -9 "$pid" 2>/dev/null || true
done
echo "Done."

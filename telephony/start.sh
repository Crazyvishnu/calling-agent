#!/bin/sh
set -eu
asterisk -f -vvv &
ast_pid=$!
trap 'kill "$ast_pid" "$relay_pid" 2>/dev/null || true' EXIT INT TERM
for attempt in $(seq 1 50); do
    if asterisk -rx 'core show uptime' >/dev/null 2>&1; then break; fi
    sleep 0.1
done
python3 /opt/akki/audio_relay.py &
relay_pid=$!
wait "$ast_pid"

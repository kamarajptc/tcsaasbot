#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

terminate_pid() {
    local pid="$1"
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "Killing process $pid..."
        kill "$pid" 2>/dev/null || true
    fi
}

echo "🛑 Stopping all TangentCloud AI Bots services..."

if [ -f "$ROOT_DIR/.pids" ]; then
    while read -r pid; do
        [ -n "${pid:-}" ] || continue
        terminate_pid "$pid"
    done < "$ROOT_DIR/.pids"
    rm -f "$ROOT_DIR/.pids"
else
    echo "No .pids file found. Trying to kill by port..."
fi

for port in 9100 9101 9102; do
    pids="$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        for pid in $pids; do
            terminate_pid "$pid"
        done
    fi
done

sleep 2

for port in 9100 9101 9102; do
    pids="$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        echo "Force killing processes on port $port..."
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
    fi
done

echo "✅ All services stopped."

#!/bin/bash

set -euo pipefail

# Port Configuration
BACKEND_PORT=9100
DASHBOARD_PORT=9101
MOBILE_PORT=9102

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Starting TangentCloud AI Bots Unified Environment..."

# Function to track PIDs
track_pid() {
    echo "$1" >> "$ROOT_DIR/.pids"
}

start_detached() {
    local name="$1"
    local logfile="$2"
    shift 2
    (
        cd "$ROOT_DIR"
        nohup "$@" > "$logfile" 2>&1 < /dev/null &
        echo $!
    )
}

wait_for_port() {
    local port="$1"
    local label="$2"
    local attempts=20

    while [ "$attempts" -gt 0 ]; do
        if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo "✅ $label is listening on port $port"
            return 0
        fi
        sleep 1
        attempts=$((attempts - 1))
    done

    echo "⚠️  $label did not bind to port $port. Check logs in $(basename "$ROOT_DIR")/."
    return 1
}

# Clear old PIDs
rm -f "$ROOT_DIR/.pids"
touch "$ROOT_DIR/.pids"

# 1. Start Backend
echo "📡 Starting Backend on port $BACKEND_PORT..."
backend_pid="$(start_detached "backend" "$ROOT_DIR/backend.out" bash -lc "cd '$ROOT_DIR/backend' && if [ -d venv ]; then source venv/bin/activate; fi && uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT")"
track_pid "$backend_pid"

# 2. Start Dashboard
echo "💻 Starting Dashboard on port $DASHBOARD_PORT..."
dashboard_pid="$(start_detached "dashboard" "$ROOT_DIR/dashboard.out" bash -lc "cd '$ROOT_DIR/dashboard' && npm run dev -- --hostname 0.0.0.0")"
track_pid "$dashboard_pid"

# 3. Start Mobile (Expo)
echo "📱 Starting Mobile on port $MOBILE_PORT..."
mobile_pid="$(start_detached "mobile" "$ROOT_DIR/mobile.out" bash -lc "cd '$ROOT_DIR/mobile' && CI=1 npx expo start --port $MOBILE_PORT")"
track_pid "$mobile_pid"

backend_ok=0
dashboard_ok=0
mobile_ok=0

wait_for_port "$BACKEND_PORT" "Backend" || backend_ok=1
wait_for_port "$DASHBOARD_PORT" "Dashboard" || dashboard_ok=1
wait_for_port "$MOBILE_PORT" "Mobile" || mobile_ok=1

echo "------------------------------------------------"
if [ "$backend_ok" -eq 0 ] && [ "$dashboard_ok" -eq 0 ] && [ "$mobile_ok" -eq 0 ]; then
    echo "✅ All services initiated!"
else
    echo "⚠️  Some services did not start correctly."
fi
echo "📡 Backend:   http://localhost:$BACKEND_PORT"
echo "💻 Dashboard: http://localhost:$DASHBOARD_PORT"
echo "📱 Mobile:    http://localhost:$MOBILE_PORT"
echo "------------------------------------------------"
echo "Logs are available in: backend.out, dashboard.out, mobile.out"

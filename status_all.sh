#!/bin/bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

services=(
  "Backend:9100:$ROOT_DIR/backend.out"
  "Dashboard:9101:$ROOT_DIR/dashboard.out"
  "Mobile:9102:$ROOT_DIR/mobile.out"
)

echo "📊 TangentCloud AI Bots service status"
echo "Repository: $ROOT_DIR"

if [ -f "$ROOT_DIR/.pids" ]; then
  echo "Launcher PIDs: $(tr '\n' ' ' < "$ROOT_DIR/.pids")"
else
  echo "Launcher PIDs: none"
fi

echo "------------------------------------------------"

for entry in "${services[@]}"; do
  name="${entry%%:*}"
  rest="${entry#*:}"
  port="${rest%%:*}"
  logfile="${rest#*:}"

  pids="$(lsof -tiTCP:$port -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "✅ $name is listening on port $port (pid: $(echo "$pids" | tr '\n' ' '))"
  else
    echo "❌ $name is not listening on port $port"
    if [ -f "$logfile" ]; then
      echo "Last log lines from $(basename "$logfile"):"
      tail -n 10 "$logfile" || true
    fi
  fi
  echo "------------------------------------------------"
done

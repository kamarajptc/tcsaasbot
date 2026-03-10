#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/tcsaasbot
ENV_FILE="$ROOT/.env.droplet"
COMPOSE_FILE="$ROOT/docker-compose.droplet.yml"
NGINX_TEMPLATE="$ROOT/infra/do/nginx/tcsaasbot.conf.template"
NGINX_SITE=/etc/nginx/sites-available/tcsaasbot
cd "$ROOT"

echo "Starting remote deploy at $(date)"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy .env.droplet.example and fill in production values." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; install Docker Engine before running this script." >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose plugin not found; install Docker Compose v2 before running this script." >&2
  exit 1
fi

mkdir -p "$ROOT/artifacts" "$ROOT/qdrant_db"

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull --ignore-buildable || true
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --build

APP_DOMAIN=$(grep '^APP_DOMAIN=' "$ENV_FILE" | head -n1 | cut -d= -f2-)

if [ -n "${APP_DOMAIN:-}" ] && [ -f "$NGINX_TEMPLATE" ]; then
  if ! command -v nginx >/dev/null 2>&1; then
    echo "Installing nginx"
    sudo apt-get update
    sudo apt-get install -y nginx
  fi

  sed "s/__APP_DOMAIN__/${APP_DOMAIN}/g" "$NGINX_TEMPLATE" | sudo tee "$NGINX_SITE" >/dev/null
  sudo ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/tcsaasbot
  if [ -f /etc/nginx/sites-enabled/default ]; then
    sudo rm -f /etc/nginx/sites-enabled/default
  fi
  sudo nginx -t
  sudo systemctl reload nginx || sudo systemctl restart nginx
fi

echo "Running container status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "Remote deploy finished at $(date)"

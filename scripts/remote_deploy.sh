#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/tcsaasbot
ENV_FILE="$ROOT/.env.droplet"
COMPOSE_FILE="$ROOT/docker-compose.droplet.yml"
NGINX_TEMPLATE="$ROOT/infra/do/nginx/tcsaasbot.conf.template"
NGINX_SITE=/etc/nginx/sites-available/tcsaasbot

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
elif command -v sudo >/dev/null 2>&1 && sudo -n true >/dev/null 2>&1; then
  SUDO="sudo -n"
else
  SUDO=""
fi

run_as_root() {
  if [ -n "$SUDO" ]; then
    $SUDO "$@"
    return
  fi

  if [ "$(id -u)" -eq 0 ]; then
    "$@"
    return
  fi

  echo "This step requires root privileges, but passwordless sudo is not available." >&2
  exit 1
}

dump_compose_diagnostics() {
  echo "Deployment failed. Container status:" >&2
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps >&2 || true
  echo "API logs:" >&2
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=200 api >&2 || true
  echo "Web logs:" >&2
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=200 web >&2 || true
  echo "Redis logs:" >&2
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs --tail=100 redis >&2 || true
}

trap dump_compose_diagnostics ERR

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

# Free unused Docker artifacts before pulling new images. This keeps
# routine deploys from failing when the droplet accumulates old layers.
docker image prune -af >/dev/null || true
docker builder prune -af >/dev/null || true

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --remove-orphans || true
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

APP_DOMAIN=$(grep '^APP_DOMAIN=' "$ENV_FILE" | head -n1 | cut -d= -f2-)

if [ -n "${APP_DOMAIN:-}" ] && [ -f "$NGINX_TEMPLATE" ]; then
  if ! command -v nginx >/dev/null 2>&1; then
    echo "Installing nginx"
    run_as_root apt-get update
    run_as_root apt-get install -y nginx
  fi

  sed "s/__APP_DOMAIN__/${APP_DOMAIN}/g" "$NGINX_TEMPLATE" | run_as_root tee "$NGINX_SITE" >/dev/null
  run_as_root ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/tcsaasbot
  if [ -f /etc/nginx/sites-enabled/default ]; then
    run_as_root rm -f /etc/nginx/sites-enabled/default
  fi
  run_as_root nginx -t
  run_as_root systemctl reload nginx || run_as_root systemctl restart nginx
fi

echo "Running container status"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

echo "Remote deploy finished at $(date)"

#!/usr/bin/env bash
set -euo pipefail

# Gather DigitalOcean droplet and managed DB details and optionally test SSH.
# Usage:
#  DO_REGION=blr1 DROPLET_NAME=tcsaasbot SSH_USER=ubuntu SSH_KEY_PATH=~/.ssh/id_rsa DB_CLUSTER_NAME=tcsaasbot-pg DB_NAME=tcsaasbot ./scripts/get_deployment_details.sh

DO_REGION="${DO_REGION:-nyc1}"
DROPLET_NAME="${DROPLET_NAME:-tcsaasbot}"
DB_CLUSTER_NAME="${DB_CLUSTER_NAME:-}"
DB_URI="${DB_URI:-}"
DB_NAME="${DB_NAME:-tcsaasbot}"
SSH_USER="${SSH_USER:-ubuntu}"
SSH_KEY_PATH="${SSH_KEY_PATH:-}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd doctl
require_cmd python3

echo "Looking up droplet: ${DROPLET_NAME} (region: ${DO_REGION})"
DROPLET_LINE="$(doctl compute droplet list --format ID,Name,PublicIPv4 --no-header | awk -v n="$DROPLET_NAME" '$2==n{print $1" "$3; exit}')" || true
if [[ -z "$DROPLET_LINE" ]]; then
  echo "Droplet not found with name: ${DROPLET_NAME}" >&2
else
  DROPLET_ID="$(echo "$DROPLET_LINE" | awk '{print $1}')"
  DROPLET_IP="$(echo "$DROPLET_LINE" | awk '{print $2}')"
  echo "Droplet ID: $DROPLET_ID"
  echo "Droplet IP: $DROPLET_IP"
fi

if [[ -n "${SSH_KEY_PATH}" && -n "${DROPLET_IP:-}" ]]; then
  echo "Testing SSH to ${SSH_USER}@${DROPLET_IP} using key ${SSH_KEY_PATH} (timeout 5s)"
  set +e
  ssh -i "${SSH_KEY_PATH}" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=no "${SSH_USER}@${DROPLET_IP}" echo ok >/dev/null 2>&1
  SSH_EXIT=$?
  set -e
  if [[ $SSH_EXIT -eq 0 ]]; then
    echo "SSH test succeeded"
  else
    echo "SSH test failed (exit $SSH_EXIT). Verify key, user and droplet firewall." >&2
  fi
else
  if [[ -z "${SSH_KEY_PATH}" ]]; then
    echo "SSH_KEY_PATH not provided; skipping SSH test"
  else
    echo "Droplet IP unknown; cannot test SSH"
  fi
fi

convert_raw_uri_to_sqlalchemy() {
  raw_uri="$1"
  db_name="$2"
  python3 - "$raw_uri" "$db_name" <<'PY'
import sys
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

raw_uri = sys.argv[1].strip()
db_name = sys.argv[2].strip()
if raw_uri.startswith("postgres://"):
    raw_uri = raw_uri.replace("postgres://", "postgresql://", 1)
if raw_uri.startswith("postgresql://"):
    raw_uri = raw_uri.replace("postgresql://", "postgresql+psycopg://", 1)

parts = urlparse(raw_uri)
query = dict(parse_qsl(parts.query, keep_blank_values=True))
query.setdefault("sslmode", "require")

new_parts = parts._replace(path=f"/{db_name}", query=urlencode(query))
print(urlunparse(new_parts))
PY
}

if [[ -n "${DB_CLUSTER_NAME}" ]]; then
  echo "Looking up DB cluster: ${DB_CLUSTER_NAME}"
  DB_CLUSTER_ID="$(doctl databases list --format ID,Name --no-header | awk -v n="$DB_CLUSTER_NAME" '$2==n{print $1; exit}')" || true
  if [[ -z "$DB_CLUSTER_ID" ]]; then
    echo "DB cluster not found: ${DB_CLUSTER_NAME}" >&2
  else
    RAW_URI="$(doctl databases connection "$DB_CLUSTER_ID" --format URI --no-header | head -n1)"
    if [[ -z "$RAW_URI" ]]; then
      echo "Could not fetch DB connection URI for cluster ${DB_CLUSTER_NAME}" >&2
    else
      echo "Converting managed DB URI to SQLAlchemy format (db name: ${DB_NAME})"
      SQLALCHEMY_DATABASE_URL="$(convert_raw_uri_to_sqlalchemy "$RAW_URI" "$DB_NAME")"
      echo "DATABASE_URL=${SQLALCHEMY_DATABASE_URL}"
    fi
  fi
elif [[ -n "${DB_URI}" ]]; then
  echo "Converting provided DB URI to SQLAlchemy format (db name: ${DB_NAME})"
  SQLALCHEMY_DATABASE_URL="$(convert_raw_uri_to_sqlalchemy "$DB_URI" "$DB_NAME")"
  echo "DATABASE_URL=${SQLALCHEMY_DATABASE_URL}"
else
  echo "No DB_CLUSTER_NAME or DB_URI provided; skipping DB lookup"
fi

echo
echo "Example: write to backend/.env or export in systemd unit as:"
echo "  DATABASE_URL='<the value above>'"

exit 0

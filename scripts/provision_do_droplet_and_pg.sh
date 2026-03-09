#!/usr/bin/env bash
set -euo pipefail

# Provision a DigitalOcean Droplet and a Managed PostgreSQL cluster, then print
# the SQLAlchemy DATABASE_URL and migration command for this repo.

DO_REGION="${DO_REGION:-nyc1}"
DROPLET_NAME="${DROPLET_NAME:-tcsaasbot-api}"
DROPLET_SIZE="${DROPLET_SIZE:-s-2vcpu-4gb}"
DROPLET_IMAGE="${DROPLET_IMAGE:-ubuntu-24-04-x64}"
DROPLET_TAG="${DROPLET_TAG:-tcsaasbot-api}"
DB_CLUSTER_NAME="${DB_CLUSTER_NAME:-tcsaasbot-pg}"
DB_ENGINE="${DB_ENGINE:-pg}"
DB_SIZE="${DB_SIZE:-db-s-1vcpu-1gb}"
DB_NODES="${DB_NODES:-1}"
DB_NAME="${DB_NAME:-tcsaasbot}"
SSH_KEY_IDS="${SSH_KEY_IDS:-}"
USER_DATA_FILE="${USER_DATA_FILE:-}"
RUN_MIGRATION="${RUN_MIGRATION:-false}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DATABASE_URL="${SOURCE_DATABASE_URL:-sqlite:///${ROOT_DIR}/backend/sql_app.db}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd doctl
require_cmd awk
require_cmd python3

if ! doctl auth list >/dev/null 2>&1; then
  cat >&2 <<'EOF'
doctl is not authenticated.
Run:
  doctl auth init
Then re-run this script.
EOF
  exit 1
fi

if [[ -z "${SSH_KEY_IDS}" ]]; then
  cat >&2 <<'EOF'
SSH_KEY_IDS is required.
Example:
  export SSH_KEY_IDS="$(doctl compute ssh-key list --format ID --no-header | head -n1)"
EOF
  exit 1
fi

if [[ -n "${USER_DATA_FILE}" && ! -f "${USER_DATA_FILE}" ]]; then
  echo "USER_DATA_FILE does not exist: ${USER_DATA_FILE}" >&2
  exit 1
fi

find_droplet_id() {
  doctl compute droplet list --format ID,Name --no-header \
    | awk -v n="$DROPLET_NAME" '$2==n {print $1; exit}'
}

find_db_cluster_id() {
  doctl databases list --format ID,Name --no-header \
    | awk -v n="$DB_CLUSTER_NAME" '$2==n {print $1; exit}'
}

echo "Checking droplet: ${DROPLET_NAME}"
DROPLET_ID="$(find_droplet_id || true)"
if [[ -z "${DROPLET_ID}" ]]; then
  echo "Creating droplet ${DROPLET_NAME} in ${DO_REGION}"
  create_args=(
    compute droplet create "${DROPLET_NAME}"
    --region "${DO_REGION}"
    --size "${DROPLET_SIZE}"
    --image "${DROPLET_IMAGE}"
    --tag-names "${DROPLET_TAG}"
    --ssh-keys "${SSH_KEY_IDS}"
    --wait
  )
  if [[ -n "${USER_DATA_FILE}" ]]; then
    create_args+=(--user-data-file "${USER_DATA_FILE}")
  fi
  doctl "${create_args[@]}" >/dev/null
  DROPLET_ID="$(find_droplet_id)"
fi

if [[ -z "${DROPLET_ID}" ]]; then
  echo "Failed to find droplet ID for ${DROPLET_NAME}" >&2
  exit 1
fi

DROPLET_IP="$(doctl compute droplet get "${DROPLET_ID}" --format PublicIPv4 --no-header)"
echo "Droplet ready: id=${DROPLET_ID} ip=${DROPLET_IP}"

echo "Checking database cluster: ${DB_CLUSTER_NAME}"
DB_CLUSTER_ID="$(find_db_cluster_id || true)"
if [[ -z "${DB_CLUSTER_ID}" ]]; then
  echo "Creating managed PostgreSQL cluster ${DB_CLUSTER_NAME}"
  doctl databases create "${DB_CLUSTER_NAME}" \
    --engine "${DB_ENGINE}" \
    --region "${DO_REGION}" \
    --size "${DB_SIZE}" \
    --num-nodes "${DB_NODES}" >/dev/null
  for _ in $(seq 1 30); do
    DB_CLUSTER_ID="$(find_db_cluster_id || true)"
    [[ -n "${DB_CLUSTER_ID}" ]] && break
    sleep 2
  done
fi

if [[ -z "${DB_CLUSTER_ID}" ]]; then
  echo "Failed to find database cluster ID for ${DB_CLUSTER_NAME}" >&2
  exit 1
fi

echo "Waiting for database cluster to become online"
for _ in $(seq 1 90); do
  DB_STATUS="$(doctl databases get "${DB_CLUSTER_ID}" --format Status --no-header || true)"
  if [[ "${DB_STATUS}" == "online" ]]; then
    break
  fi
  sleep 5
done
DB_STATUS="$(doctl databases get "${DB_CLUSTER_ID}" --format Status --no-header)"
if [[ "${DB_STATUS}" != "online" ]]; then
  echo "Database cluster is not online. Current status: ${DB_STATUS}" >&2
  exit 1
fi

if ! doctl databases db list "${DB_CLUSTER_ID}" --format Name --no-header | grep -Fxq "${DB_NAME}"; then
  echo "Creating database ${DB_NAME}"
  doctl databases db create "${DB_CLUSTER_ID}" "${DB_NAME}" >/dev/null
fi

if ! doctl databases firewalls list "${DB_CLUSTER_ID}" --format Type,Value --no-header \
  | awk '$1=="droplet" {print $2}' | grep -Fxq "${DROPLET_ID}"; then
  echo "Allowing droplet ${DROPLET_ID} to access managed PostgreSQL"
  doctl databases firewalls append "${DB_CLUSTER_ID}" --rule "droplet:${DROPLET_ID}" >/dev/null
fi

RAW_URI="$(doctl databases connection "${DB_CLUSTER_ID}" --format URI --no-header | head -n1)"
if [[ -z "${RAW_URI}" ]]; then
  echo "Could not fetch database connection URI" >&2
  exit 1
fi

SQLALCHEMY_DATABASE_URL="$(python3 - "$RAW_URI" "$DB_NAME" <<'PY'
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
)"

echo
echo "Provisioning complete:"
echo "  Droplet ID:   ${DROPLET_ID}"
echo "  Droplet IP:   ${DROPLET_IP}"
echo "  DB Cluster ID:${DB_CLUSTER_ID}"
echo "  DB Name:      ${DB_NAME}"
echo
echo "Use this in backend/.env (or runtime env):"
echo "DATABASE_URL=${SQLALCHEMY_DATABASE_URL}"
echo
echo "Run data migration from this repo root:"
echo "PYTHONPATH=backend SOURCE_DATABASE_URL='${SOURCE_DATABASE_URL}' TARGET_DATABASE_URL='${SQLALCHEMY_DATABASE_URL}' python3 scripts/migrate_sqlite_to_postgres.py"

if [[ "${RUN_MIGRATION}" == "true" ]]; then
  echo
  echo "RUN_MIGRATION=true set: starting migration now."
  PYTHONPATH=backend \
    SOURCE_DATABASE_URL="${SOURCE_DATABASE_URL}" \
    TARGET_DATABASE_URL="${SQLALCHEMY_DATABASE_URL}" \
    python3 "${ROOT_DIR}/scripts/migrate_sqlite_to_postgres.py"
fi

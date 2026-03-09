# DigitalOcean Droplet + Managed PostgreSQL

This guide provisions:
- One Droplet for the backend service
- One Managed PostgreSQL cluster as a separate service
- Secure DB access from that Droplet
- SQLite -> PostgreSQL data migration for this repo

## 1. Install and authenticate `doctl`

```bash
brew install doctl
doctl auth init
doctl auth list
```

## 2. Pick an SSH key ID

```bash
doctl compute ssh-key list --format ID,Name
export SSH_KEY_IDS="<your_ssh_key_id>"
```

## 3. Provision Droplet + managed PostgreSQL

From repo root:

```bash
export DO_REGION=nyc1
export DROPLET_NAME=tcsaasbot-api
export DB_CLUSTER_NAME=tcsaasbot-pg
export DB_NAME=tcsaasbot

./scripts/provision_do_droplet_and_pg.sh
```

Optional (run migration automatically at the end):

```bash
RUN_MIGRATION=true ./scripts/provision_do_droplet_and_pg.sh
```

The script prints:
- Droplet IP
- Managed DB cluster ID
- Production `DATABASE_URL` (`postgresql+psycopg://...`)
- Exact migration command

## 4. Migrate existing SQLite data

If you did not use `RUN_MIGRATION=true`, run the printed command manually:

```bash
PYTHONPATH=backend \
SOURCE_DATABASE_URL="sqlite:////absolute/path/to/backend/sql_app.db" \
TARGET_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@HOST:25060/tcsaasbot?sslmode=require" \
python3 scripts/migrate_sqlite_to_postgres.py
```

## 5. Point backend to managed PostgreSQL

Set on Droplet runtime environment:

```bash
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:25060/tcsaasbot?sslmode=require
ENV=production
```

Then restart backend service/container on the Droplet.

## 6. Validate

```bash
curl -f http://<droplet-ip>:9100/health || curl -f http://<droplet-ip>:9100/healthz
```

Check data in PostgreSQL:

```bash
psql "postgresql://USER:PASSWORD@HOST:25060/tcsaasbot?sslmode=require" -c '\dt'
```

## Notes

- The script is idempotent for existing resource names (reuses existing droplet/cluster).
- For production hardening, keep DB firewall restricted to the droplet and do not allow `0.0.0.0/0`.
- This repo still uses local file-backed vector storage (`QDRANT_PATH`) by default.

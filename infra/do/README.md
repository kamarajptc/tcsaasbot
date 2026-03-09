# DigitalOcean Deployment Assets

This directory is the SaaS-hosting target for DigitalOcean.

Current entrypoint:
- `.do/app.yaml` for App Platform
- `docker-compose.saas.yml` for local production-like validation
- `docs/deployment/digitalocean-droplet-managed-postgres.md` for Droplet + Managed PostgreSQL
- `scripts/provision_do_droplet_and_pg.sh` for provisioning/migration bootstrap

Recommended first deployment:
1. Deploy `api` and `dashboard` on App Platform.
2. Use Managed PostgreSQL and Managed Redis.
3. Keep vector storage local only for MVP. Move to managed/shared vector infrastructure before scaling.

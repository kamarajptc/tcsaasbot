# DigitalOcean SaaS Deployment

## Scope
This repo remains the single codebase. The backend is being refactored into a modular monolith and deployed first on DigitalOcean.

## Runtime Shape
- `backend` FastAPI API deployed as one containerized service
- `dashboard` Next.js deployed as a separate App Platform service
- Existing DigitalOcean Managed PostgreSQL for transactional data
- Existing or future DigitalOcean Redis for cache/rate limiting/background coordination
- Chroma remains local-file backed for MVP only

## Why this shape
- Lowest operating complexity for early SaaS hosting
- Cheap enough to run before enterprise-scale traffic exists
- Keeps the app portable for later extraction or AWS migration

## Current artifacts
- Backend Dockerfile: `backend/Dockerfile`
- Local prod-like compose: `docker-compose.saas.yml`
- App Platform starter spec using external managed services: `.do/app.yaml`

## Required environment variables
- `DATABASE_URL`
- `REDIS_URL`
- `OPENAI_API_KEY` or `GOOGLE_API_KEY`
- `SECRET_KEY`
- `AUTH_PASSWORD`
- `FRONTEND_URL`

## Expected managed services
- DigitalOcean Managed PostgreSQL already provisioned by you
- DigitalOcean Redis strongly recommended before production traffic

Example `DATABASE_URL`:

```text
postgresql+psycopg://USER:PASSWORD@HOST:25060/DATABASE?sslmode=require
```

## Important limitations
- Chroma on local disk is not a long-term scaling answer.
- App Platform ephemeral filesystem means local persistence is non-durable. For production, move vector persistence to a managed external service or separate persistent worker host.
- SQLite must not be used on App Platform.

## Recommended DO-first roadmap
1. Switch `DATABASE_URL` to Managed PostgreSQL.
2. Externalize vector persistence.
3. Move queueing from in-memory to Redis-backed workers.
4. Add object storage adapter for Spaces.
5. Add CI to validate Docker build and smoke-test `/healthz`.

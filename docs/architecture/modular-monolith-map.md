# Modular Monolith Migration Map

This repo is now on a non-destructive modular-monolith path.

## Current state
- Existing FastAPI endpoints remain under `backend/app/api/v1`
- Existing business services remain under `backend/app/services`
- New composition root is `backend/app/bootstrap`
- Target module boundaries live under `backend/app/modules`
- Infrastructure portability layer lives under `backend/app/infrastructure`

## Immediate code ownership map
- `backend/app/api/v1/chat.py` -> `chat`
- `backend/app/api/v1/ingest.py` -> `knowledge_ingestion`
- `backend/app/services/rag_service.py` -> `ai_orchestration` + `knowledge_retrieval`
- `backend/app/api/v1/leads.py` -> `lead_management`
- `backend/app/api/v1/analytics.py` -> `analytics`
- `backend/app/api/v1/analytics_enterprise.py` -> `analytics`
- `backend/app/api/v1/billing.py` -> `billing`
- `backend/app/api/v1/integrations.py` -> `integrations`
- `backend/app/services/email_service.py` -> `notifications`
- `backend/app/core/security.py` -> `identity`
- `backend/app/models/bot.py` -> `bot_management`
- `backend/app/api/v1/endpoints/dashboard.py` -> `admin_platform`

## Refactor sequence
1. Keep public route contracts stable.
2. Move orchestration logic from `api/v1/*.py` into module application services.
3. Move provider-specific code behind `app/infrastructure/ports`.
4. Introduce per-module DTOs and query services.
5. Add architecture tests to block cross-module imports.
6. Split persistence ownership module-by-module.

## Current portability status
- App factory added
- Router registry added
- Storage/queue/cache/secrets interfaces added
- Local/env/redis adapters added
- Backend container added
- DigitalOcean SaaS assets added

## Next code moves
1. Extract `rag_service.py` into:
   - `modules/knowledge_retrieval/application/*`
   - `modules/ai_orchestration/application/*`
2. Extract quota logic from `core/usage_limits.py` into `modules/billing`
3. Move bot CRUD from dashboard endpoints into `modules/bot_management`
4. Introduce Redis-backed queue adapter and Spaces adapter

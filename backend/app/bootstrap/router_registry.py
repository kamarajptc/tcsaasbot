from collections.abc import Iterable

from fastapi import FastAPI

from app.api.v1 import (
    admin_rate_limits,
    agent_transfer,
    analytics,
    analytics_enterprise,
    billing,
    chat,
    flows,
    ingest,
    integrations,
    leads,
    quality,
)
from app.api.v1.endpoints import auth, dashboard


ROUTERS = (
    (chat.router, "/api/v1/chat", ("chat",)),
    (ingest.router, "/api/v1/ingest", ("ingest",)),
    (leads.router, "/api/v1/leads", ("leads",)),
    (billing.router, "/api/v1/billing", ("billing",)),
    (analytics.router, "/api/v1/analytics", ("analytics",)),
    (admin_rate_limits.router, "/api/v1/admin/rate-limits", ("admin-rate-limits",)),
    (analytics_enterprise.router, "/api/v1/analytics/enterprise", ("analytics-enterprise",)),
    (dashboard.router, "/api/v1/dashboard", ("dashboard",)),
    (flows.router, "/api/v1/flows", ("flows",)),
    (agent_transfer.router, "/api/v1/agent-transfer", ("agent-transfer",)),
    (integrations.router, "/api/v1/integrations", ("integrations",)),
    (quality.router, "/api/v1/quality", ("quality",)),
    (auth.router, "/api/v1/auth", ("auth",)),
)


def include_application_routers(app: FastAPI, routers: Iterable = ROUTERS) -> None:
    for router, prefix, tags in routers:
        app.include_router(router, prefix=prefix, tags=list(tags))

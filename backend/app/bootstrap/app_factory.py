from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bootstrap.router_registry import include_application_routers
from app.core.config import get_settings
from app.core.database import init_db
from app.core.http_security import SecurityHeadersMiddleware
from app.core.logging import RequestLoggingMiddleware, logger, setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.telemetry import setup_telemetry


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    init_db()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "application_started",
            extra={
                "app_name": settings.APP_NAME,
                "database_url": settings.DATABASE_URL.split("///")[-1],
                "storage_backend": settings.STORAGE_BACKEND,
                "queue_backend": settings.QUEUE_BACKEND,
                "cache_backend": settings.CACHE_BACKEND,
            },
        )
        yield
        logger.info("application_shutdown")

    app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
    setup_telemetry(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    include_application_routers(app)

    @app.get("/")
    def read_root() -> dict[str, str]:
        return {"message": f"Welcome to {settings.APP_NAME} API"}

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "env": settings.ENV}

    return app

import logging
import sys
import time
from pythonjsonlogger import jsonlogger
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

def setup_logging():
    # Instrument logging for OpenTelemetry (adds trace_id, span_id to log records)
    LoggingInstrumentor().instrument(set_logging_format=False)

    log_handler = logging.StreamHandler(sys.stdout)
    
    # Use JSON format for Loki/Promtail compatibility
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s %(span_id)s'
    )
    log_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(log_handler)

    # Specific logger levels to reduce noise
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

logger = logging.getLogger("TangentCloud")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs every incoming request with:
    - HTTP method, path, query params
    - Response status code
    - Request duration in milliseconds
    - Tenant ID (from X-API-Key header)
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        tenant_id = request.headers.get("x-api-key", "anonymous")
        method = request.method
        path = request.url.path
        query = str(request.query_params) if request.query_params else ""

        logger.info(
            "request_started",
            extra={
                "http_method": method,
                "path": path,
                "query": query,
                "tenant_id": tenant_id,
            }
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                "request_failed",
                extra={
                    "http_method": method,
                    "path": path,
                    "tenant_id": tenant_id,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                }
            )
            raise

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        status_code = response.status_code
        response.headers["X-Process-Time-Ms"] = str(duration_ms)

        log_extra = {
            "http_method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "tenant_id": tenant_id,
        }

        if status_code >= 500:
            logger.error("request_completed", extra=log_extra)
        elif status_code >= 400:
            logger.warning("request_completed", extra=log_extra)
        else:
            logger.info("request_completed", extra=log_extra)

        return response

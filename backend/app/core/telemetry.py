from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
import logging
import os

logger = logging.getLogger("TangentCloud")

def setup_telemetry(app):
    """
    Sets up OpenTelemetry tracing for the FastAPI application.
    Supports both OTLP (for production/Docker) and Console (for local testing).
    """
    resource = Resource.create(attributes={
        "service.name": "TangentCloud",
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("ENV", "development")
    })

    provider = TracerProvider(resource=resource)
    
    # Always add Console exporter for local visibility
    console_processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(console_processor)

    # Add OTLP exporter only in production to avoid gRPC connection errors in development
    if os.getenv("ENV") == "production":
        try:
            otlp_exporter = OTLPSpanExporter()
            otlp_processor = BatchSpanProcessor(otlp_exporter)
            provider.add_span_processor(otlp_processor)
            logger.info("telemetry_otlp_enabled")
        except Exception:
            # Silently skip OTLP if GRPC/Collector is not available
            logger.info("telemetry_otlp_skipped", extra={"reason": "OTLP exporter initialization failed"})

    trace.set_tracer_provider(provider)

    # Instrument FastAPI automatically
    FastAPIInstrumentor.instrument_app(app)
    logger.info("telemetry_initialized", extra={
        "service_name": "TangentCloud",
        "environment": os.getenv("ENV", "development"),
        "exporters": ["console", "otlp"]
    })


def get_tracer(name: str = "TangentCloud"):
    """
    Get a named tracer for creating custom spans in business logic.
    
    Usage:
        tracer = get_tracer()
        with tracer.start_as_current_span("my_operation") as span:
            span.set_attribute("key", "value")
            # do work
    """
    return trace.get_tracer(name)

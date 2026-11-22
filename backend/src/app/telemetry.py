"""
OpenTelemetry tracing (S7.2).

Enabled only when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set. Spans go over
OTLP/gRPC to the collector, which forwards them to Jaeger.

Auto-instrumented: FastAPI HTTP routes, SQLAlchemy (asyncpg underneath) and
Redis commands. WebSocket connections are excluded from the ASGI
instrumentation: one span per socket would last for the whole connection and
put every message into a single trace. Instead ``routers/ws.py`` starts a new
trace per event, and ``services/pubsub.py`` carries the trace context in the
Redis envelope so delivery on every replica joins the sender's trace.

Sampling follows the standard ``OTEL_TRACES_SAMPLER`` /
``OTEL_TRACES_SAMPLER_ARG`` variables (default: every trace).
"""

import socket

import structlog
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import (  # pyright: ignore[reportMissingTypeStubs]
    SQLAlchemyInstrumentor,
)
from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID, SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)

from app.config import Settings
from app.database import engine

logger = structlog.get_logger(__name__)

# Regexes searched in the full request URL. Probes and scrapes run every few
# seconds and would bury real traffic.
_EXCLUDED_URLS = "/health$,/ready$,/metrics$,/ws/"

_provider: TracerProvider | None = None


def configure_tracing(
    settings: Settings, *, span_exporter: SpanExporter | None = None
) -> TracerProvider | None:
    """
    Install the process-wide tracer provider and library instrumentation.

    Idempotent: the SDK accepts one global provider per process, so later
    calls return the first one. ``span_exporter`` replaces the OTLP exporter
    (tests pass an in-memory one) and is exported synchronously.
    """
    global _provider
    if not settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        return None
    if _provider is not None:
        return _provider

    resource = Resource.create(
        {
            SERVICE_NAME: settings.OTEL_SERVICE_NAME,
            # Container hostname: tells replicas apart in a cross-instance trace.
            SERVICE_INSTANCE_ID: socket.gethostname(),
        }
    )
    provider = TracerProvider(resource=resource)
    if span_exporter is None:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)

    # Also wraps create_engine / create_async_engine for engines made later.
    SQLAlchemyInstrumentor().instrument(  # pyright: ignore[reportUnknownMemberType]
        engine=engine.sync_engine, tracer_provider=provider
    )
    # Commands only (PUBLISH, PING, ...). The pub/sub listener's polling is
    # not a command, so it does not produce a span per poll.
    RedisInstrumentor().instrument(tracer_provider=provider)  # pyright: ignore[reportUnknownMemberType]

    _provider = provider
    logger.info(
        "tracing_enabled",
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        service=settings.OTEL_SERVICE_NAME,
    )
    return provider


def setup_telemetry(
    app: FastAPI, settings: Settings, *, span_exporter: SpanExporter | None = None
) -> bool:
    """Trace *app*'s HTTP routes. Returns False (and does nothing) if disabled."""
    provider = configure_tracing(settings, span_exporter=span_exporter)
    if provider is None:
        return False
    FastAPIInstrumentor.instrument_app(
        app, tracer_provider=provider, excluded_urls=_EXCLUDED_URLS
    )
    return True

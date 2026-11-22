"""
OpenTelemetry tracing (S7.2).

The SDK allows one global TracerProvider per process. ``tracing`` installs a
provider with an in-memory exporter the first time it is used; every test
clears the exporter first. Other test modules leave
``OTEL_EXPORTER_OTLP_ENDPOINT`` blank (see ``tests/__init__.py``), so they
never install a provider.

Pub/Sub and WebSocket tests use the real Redis: `docker compose up -d redis`.
"""

import json
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import redis.asyncio as aioredis
import sqlalchemy.ext.asyncio as sa_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient

import app.routers.ws as ws_module
import app.telemetry as telemetry
from app.config import Settings, get_settings
from app.main import create_app
from tests.conftest import TEST_DATABASE_URL, make_token
from tests.factories import ChannelFactory, ChannelMembershipFactory, UserFactory
from tests.test_pubsub_fanout import FakeWebSocket, instances, wait_until

REDIS_URL = get_settings().REDIS_URL
_ENABLED = Settings(OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4317")
_EXPORTER = InMemorySpanExporter()


@pytest.fixture
def tracing() -> Iterator[InMemorySpanExporter]:
    telemetry.configure_tracing(_ENABLED, span_exporter=_EXPORTER)
    _EXPORTER.clear()
    yield _EXPORTER
    _EXPORTER.clear()


def named(exporter: InMemorySpanExporter, name: str) -> list[ReadableSpan]:
    return [s for s in exporter.get_finished_spans() if s.name == name]


def one(exporter: InMemorySpanExporter, name: str) -> ReadableSpan:
    spans = named(exporter, name)
    assert len(spans) == 1, (name, [s.name for s in exporter.get_finished_spans()])
    return spans[0]


def parent_id(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent is not None else None


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.span_id


def trace_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.trace_id


def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before timeout")
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Setup gating
# ---------------------------------------------------------------------------


def test_setup_is_a_no_op_without_an_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fail(*_: Any, **__: Any) -> None:
        raise AssertionError("must not install a tracer provider")

    monkeypatch.setattr(trace, "set_tracer_provider", _fail)
    app = FastAPI()

    assert (
        telemetry.setup_telemetry(app, Settings(OTEL_EXPORTER_OTLP_ENDPOINT=""))
        is False
    )
    assert not getattr(app, "_is_instrumented_by_opentelemetry", False)


def test_tests_run_with_tracing_disabled() -> None:
    assert get_settings().OTEL_EXPORTER_OTLP_ENDPOINT == ""


def test_resource_names_the_service_and_replica(tracing: InMemorySpanExporter) -> None:
    with trace.get_tracer(__name__).start_as_current_span("probe"):
        pass

    attrs = one(tracing, "probe").resource.attributes
    assert attrs["service.name"] == "chat-engine-backend"
    assert attrs["service.instance.id"]


# ---------------------------------------------------------------------------
# FastAPI auto-instrumentation
# ---------------------------------------------------------------------------


async def test_http_requests_produce_server_spans_except_probes(
    tracing: InMemorySpanExporter,
) -> None:
    app = create_app()
    assert telemetry.setup_telemetry(app, _ENABLED) is True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        await c.get("/api/channels")  # 401, still traced
        await c.get("/health")
        await c.get("/metrics")

    server = [s for s in tracing.get_finished_spans() if s.kind is SpanKind.SERVER]
    assert [s.name for s in server] == ["GET /api/channels"]


# ---------------------------------------------------------------------------
# Trace context through the Redis envelope
# ---------------------------------------------------------------------------


async def test_delivery_on_another_instance_joins_the_publishers_trace(
    tracing: InMemorySpanExporter,
) -> None:
    channel_id = uuid.uuid4()
    tracer = trace.get_tracer(__name__)
    async with instances(2) as (a, b):
        ws_b = FakeWebSocket()
        await b.manager.connect(uuid.uuid4(), channel_id, ws_b)  # type: ignore[arg-type]

        with tracer.start_as_current_span("send"):
            await a.bus.publish(channel_id, {"type": "message.new", "payload": {}})
        await wait_until(lambda: len(named(tracing, "pubsub.deliver")) == 1)

    send = one(tracing, "send")
    publish = one(tracing, "pubsub.publish")
    deliver = one(tracing, "pubsub.deliver")

    assert publish.kind is SpanKind.PRODUCER
    assert parent_id(publish) == span_id(send)
    assert deliver.kind is SpanKind.CONSUMER
    assert trace_id(deliver) == trace_id(send)
    assert parent_id(deliver) == span_id(publish)
    assert deliver.attributes is not None
    assert deliver.attributes["messaging.destination.name"] == f"channel:{channel_id}"
    assert deliver.attributes["chat.local_recipients"] == 1
    # Redis auto-instrumentation: the PUBLISH command is a child of the span.
    redis_publish = one(tracing, "PUBLISH")
    assert parent_id(redis_publish) == span_id(publish)
    # The envelope does not leak into what sockets receive.
    assert ws_b.sent == [{"type": "message.new", "payload": {}}]


async def test_untraced_publish_is_delivered_without_spans(
    tracing: InMemorySpanExporter,
) -> None:
    channel_id = uuid.uuid4()
    async with instances(1) as (a,):
        ws = FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, {"type": "typing.start", "payload": {}})
        await wait_until(lambda: len(ws.sent) == 1)

    assert named(tracing, "pubsub.publish") == []
    assert named(tracing, "pubsub.deliver") == []


async def test_envelope_without_trace_context_still_delivers(
    tracing: InMemorySpanExporter,
) -> None:
    # Envelopes from an older replica (or a bad carrier) must still deliver.
    channel_id = uuid.uuid4()
    async with instances(1) as (a,):
        ws = FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]

        raw = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            for carrier in (None, {"traceparent": "garbage"}, "not-a-dict"):
                envelope = {"payload": {"n": 1}, "exclude_user_id": None}
                if carrier is not None:
                    envelope["trace"] = carrier
                await raw.publish(f"channel:{channel_id}", json.dumps(envelope))  # pyright: ignore[reportUnknownMemberType]
        finally:
            await raw.aclose()
        await wait_until(lambda: len(ws.sent) == 3)

    assert named(tracing, "pubsub.deliver") == []


# ---------------------------------------------------------------------------
# message.new end to end
# ---------------------------------------------------------------------------


async def test_message_new_trace_covers_persist_publish_and_fanout(
    tracing: InMemorySpanExporter,
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = UserFactory.build()
    channel = ChannelFactory.build(created_by=user.id)
    db_session.add(user)
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add(
        ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    )
    await db_session.commit()

    # Looked up on the module so the engine is created through the
    # instrumented factory, as app.database's is in a traced process.
    ws_engine = sa_asyncio.create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    monkeypatch.setattr(
        ws_module,
        "AsyncSessionLocal",
        sa_asyncio.async_sessionmaker(ws_engine, expire_on_commit=False),
    )
    app = create_app()
    telemetry.setup_telemetry(app, _ENABLED)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={make_token(user.id)}") as ws,
    ):
        assert ws.receive_json()["type"] == "presence.snapshot"
        ws.send_json({"type": "message.new", "payload": {"content": "traced"}})
        assert ws.receive_json()["type"] == "message.new"
        wait_for(lambda: len(named(tracing, "ws.message.new")) == 1)
        wait_for(lambda: len(named(tracing, "pubsub.deliver")) >= 2)

    root = one(tracing, "ws.message.new")
    persist = one(tracing, "db.persist")
    publish = [
        s for s in named(tracing, "pubsub.publish") if trace_id(s) == trace_id(root)
    ]
    deliver = [
        s for s in named(tracing, "pubsub.deliver") if trace_id(s) == trace_id(root)
    ]

    assert root.parent is None  # one trace per message, not per socket
    assert root.attributes is not None
    assert root.attributes["chat.channel_id"] == str(channel.id)
    assert root.attributes["chat.message_id"]
    assert parent_id(persist) == span_id(root)
    assert len(publish) == 1
    assert parent_id(publish[0]) == span_id(root)
    assert len(deliver) == 1
    assert parent_id(deliver[0]) == span_id(publish[0])
    # SQLAlchemy auto-instrumentation: the INSERT is inside db.persist.
    inserts = [
        s
        for s in tracing.get_finished_spans()
        if s.name.startswith("INSERT") and parent_id(s) == span_id(persist)
    ]
    assert inserts
    # The WebSocket connection itself is not a long-lived server span.
    assert not [s for s in tracing.get_finished_spans() if s.kind is SpanKind.SERVER]
    await ws_engine.dispose()


async def test_ws_connect_groups_auth_queries(
    tracing: InMemorySpanExporter,
    db_session: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = UserFactory.build()
    channel = ChannelFactory.build(created_by=user.id)
    db_session.add(user)
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add(
        ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    )
    await db_session.commit()

    ws_engine = sa_asyncio.create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    monkeypatch.setattr(
        ws_module,
        "AsyncSessionLocal",
        sa_asyncio.async_sessionmaker(ws_engine, expire_on_commit=False),
    )
    app = create_app()
    telemetry.setup_telemetry(app, _ENABLED)

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={make_token(user.id)}") as ws,
    ):
        assert ws.receive_json()["type"] == "presence.snapshot"
        ws.send_json({"type": "bogus"})
        assert ws.receive_json()["type"] == "error"
        wait_for(lambda: len(named(tracing, "ws.connect")) == 1)

    connect = one(tracing, "ws.connect")
    selects = [s for s in tracing.get_finished_spans() if s.name.startswith("SELECT")]
    assert selects
    assert all(parent_id(s) == span_id(connect) for s in selects)
    await ws_engine.dispose()

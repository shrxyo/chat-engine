"""
Prometheus metrics (S7.3).

Metrics live in the process-wide default registry, so values accumulate
across tests. Every assertion compares a value before and after the action.

The WebSocket tests make a real Redis round trip (like `test_ws.py`), so they
need `docker compose up -d redis`.
"""

import time
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient
from prometheus_client import REGISTRY
from starlette.testclient import TestClient

from app.services.connection_manager import ConnectionManager
from app.services.pubsub import RedisBus
from tests.conftest import make_token
from tests.factories import ChannelFactory, ChannelMembershipFactory, UserFactory
from tests.test_pubsub_fanout import FakeWebSocket
from tests.test_ws import _make_app  # pyright: ignore[reportPrivateUsage]

CUSTOM_METRICS = (
    "ws_active_connections",
    "messages_broadcast_total",
    "redis_pubsub_publish_total",
    "message_broadcast_latency_seconds",
)


def sample(name: str, labels: dict[str, str] | None = None) -> float:
    value = REGISTRY.get_sample_value(name, labels or {})
    return value if value is not None else 0.0


def wait_for(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    """Poll from the test thread while TestClient runs the app in its own."""
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before timeout")
        time.sleep(0.01)


async def _member_channel(db_session: Any) -> tuple[uuid.UUID, str]:
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
    return channel.id, make_token(user.id)


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------


async def test_metrics_endpoint_exposes_custom_metrics(client: AsyncClient) -> None:
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    for name in CUSTOM_METRICS:
        assert f"# TYPE {name} " in response.text, name


async def test_metrics_endpoint_records_http_requests(client: AsyncClient) -> None:
    labels = {"handler": "/api/channels", "method": "GET", "status": "4xx"}
    before = sample("http_requests_total", labels)

    await client.get("/api/channels")  # no token → 401

    assert sample("http_requests_total", labels) == before + 1


async def test_health_checks_are_not_instrumented(client: AsyncClient) -> None:
    await client.get("/health")

    response = await client.get("/metrics")
    assert 'handler="/health"' not in response.text


# ---------------------------------------------------------------------------
# ws_active_connections
# ---------------------------------------------------------------------------


async def test_connection_count_ignores_a_replaced_socket() -> None:
    manager = ConnectionManager()
    user_id, channel_a, channel_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    first, second, other = FakeWebSocket(), FakeWebSocket(), FakeWebSocket()

    await manager.connect(user_id, channel_a, first)  # type: ignore[arg-type]
    await manager.connect(user_id, channel_a, second)  # type: ignore[arg-type]
    await manager.connect(user_id, channel_b, other)  # type: ignore[arg-type]
    assert manager.total_connection_count() == 2

    await manager.disconnect(user_id, channel_a, first)  # type: ignore[arg-type]
    assert manager.total_connection_count() == 2

    await manager.disconnect(user_id, channel_a, second)  # type: ignore[arg-type]
    assert manager.total_connection_count() == 1


async def test_active_connections_gauge_follows_open_sockets(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel_id, token = await _member_channel(db_session)
    application = _make_app(monkeypatch)
    before = sample("ws_active_connections")

    with TestClient(application) as client:
        with client.websocket_connect(f"/ws/{channel_id}?token={token}") as ws:
            assert ws.receive_json()["type"] == "presence.snapshot"
            # Wait until the handler is in its receive loop. Leaving the block
            # earlier makes TestClient cancel the handler before it reaches
            # the `finally` that unregisters the socket.
            ws.send_json({"type": "bogus"})
            assert ws.receive_json()["type"] == "error"
            assert sample("ws_active_connections") == before + 1
        # Exiting waits for the handler to finish, and disconnect() removes
        # the socket before its first await.
        assert sample("ws_active_connections") == before


# ---------------------------------------------------------------------------
# message.new: server_ts, counters, latency
# ---------------------------------------------------------------------------


async def test_message_new_records_broadcast_metrics(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel_id, token = await _member_channel(db_session)
    application = _make_app(monkeypatch)
    sent_before = sample("messages_broadcast_total")
    latency_count_before = sample("message_broadcast_latency_seconds_count")
    latency_sum_before = sample("message_broadcast_latency_seconds_sum")
    published_before = sample("redis_pubsub_publish_total", {"result": "ok"})

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel_id}?token={token}") as ws,
    ):
        assert ws.receive_json()["type"] == "presence.snapshot"
        sent_at_ms = time.time() * 1000
        ws.send_json({"type": "message.new", "payload": {"content": "metrics"}})
        broadcast = ws.receive_json()
        received_at_ms = time.time() * 1000
        # Latency is observed after the send to every local socket returns.
        wait_for(
            lambda: (
                sample("message_broadcast_latency_seconds_count")
                == latency_count_before + 1
            )
        )

    server_ts = broadcast["payload"]["server_ts"]
    assert isinstance(server_ts, int)
    assert sent_at_ms - 1 <= server_ts <= received_at_ms + 1

    assert sample("messages_broadcast_total") == sent_before + 1
    # presence.join + message.new (+ presence.leave on close)
    assert sample("redis_pubsub_publish_total", {"result": "ok"}) >= (
        published_before + 2
    )
    observed = sample("message_broadcast_latency_seconds_sum") - latency_sum_before
    assert 0 <= observed < 5


async def test_latency_is_only_observed_for_timestamped_messages() -> None:
    manager = ConnectionManager()
    channel_id = uuid.uuid4()
    ws = FakeWebSocket()
    await manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]
    before = sample("message_broadcast_latency_seconds_count")

    await manager.broadcast_to_channel(
        channel_id, {"type": "typing.start", "payload": {"user_id": "u"}}
    )
    await manager.broadcast_to_channel(
        channel_id, {"type": "message.new", "payload": {"content": "no ts"}}
    )
    assert sample("message_broadcast_latency_seconds_count") == before

    await manager.broadcast_to_channel(
        channel_id,
        {
            "type": "message.new",
            "payload": {"content": "ts", "server_ts": int(time.time() * 1000)},
        },
    )
    assert sample("message_broadcast_latency_seconds_count") == before + 1
    assert len(ws.sent) == 3


async def test_latency_is_not_observed_without_local_sockets() -> None:
    manager = ConnectionManager()
    before = sample("message_broadcast_latency_seconds_count")

    await manager.broadcast_to_channel(
        uuid.uuid4(),
        {"type": "message.new", "payload": {"server_ts": int(time.time() * 1000)}},
    )

    assert sample("message_broadcast_latency_seconds_count") == before


# ---------------------------------------------------------------------------
# redis_pubsub_publish_total
# ---------------------------------------------------------------------------


async def test_failed_publish_is_counted_as_error() -> None:
    manager = ConnectionManager()
    bus = RedisBus("redis://127.0.0.1:1/0", deliver=manager.broadcast_to_channel)
    before = sample("redis_pubsub_publish_total", {"result": "error"})
    try:
        await bus.publish(uuid.uuid4(), {"type": "typing.start", "payload": {}})
    finally:
        await bus.stop()

    assert sample("redis_pubsub_publish_total", {"result": "error"}) == before + 1

"""
Prometheus metrics (S7.3).

Every backend container runs one uvicorn process and exposes its own
``/metrics``. Prometheus finds each replica through Docker DNS
(``infra/prometheus/prometheus.yml``), so the metrics here are plain
in-process collectors; ``PROMETHEUS_MULTIPROC_DIR`` must stay unset.

HTTP metrics (``http_requests_total``, ``http_request_duration_seconds``)
come from ``prometheus-fastapi-instrumentator``, wired in ``main.py``.
"""

import time
from typing import Any, cast

from prometheus_client import Counter, Gauge, Histogram
from prometheus_fastapi_instrumentator import metrics as http_metrics

# Created once at import. Left to itself, the instrumentator registers its
# collectors on an app's first request, and every later app in the process
# (tests build one per test) hits "duplicated timeseries" and records nothing.
HTTP_METRICS = http_metrics.default(  # pyright: ignore[reportUnknownMemberType]
    # Unlabelled histogram for overall quantiles; finer below 10ms than the
    # library default, which starts at 10ms.
    latency_highr_buckets=(
        0.001,
        0.0025,
        0.005,
        0.01,
        0.025,
        0.05,
        0.1,
        0.25,
        0.5,
        1,
        2.5,
        5,
        10,
    ),
    # Labelled by handler, so kept small.
    latency_lowr_buckets=(0.01, 0.05, 0.1, 0.5, 1),
)

# Wired to the ConnectionManager singleton in connection_manager.py, so the
# value is read from the registry itself at scrape time and cannot drift.
WS_ACTIVE_CONNECTIONS = Gauge(
    "ws_active_connections",
    "WebSocket connections currently held by this instance.",
)

MESSAGES_BROADCAST_TOTAL = Counter(
    "messages_broadcast_total",
    "Chat messages (message.new) accepted and published for fanout. Counted "
    "once, on the instance that received the message.",
)

REDIS_PUBSUB_PUBLISH_TOTAL = Counter(
    "redis_pubsub_publish_total",
    "Redis PUBLISH calls for WebSocket events, by result. An error means the "
    "event fell back to local-only delivery.",
    ["result"],
)

# Receive (handler start, server_ts) -> the send to every local socket on
# this instance returned. Observed on every instance that delivers the
# message, so it covers the cross-instance hop through Redis.
MESSAGE_BROADCAST_LATENCY_SECONDS = Histogram(
    "message_broadcast_latency_seconds",
    "Time from a message.new being received to its local fanout completing.",
    buckets=(
        0.001,
        0.0025,
        0.005,
        0.01,
        0.025,
        0.05,
        0.075,
        0.1,
        0.25,
        0.5,
        1.0,
        2.5,
    ),
)

# Pre-create both label values so dashboards show 0 rather than no data.
REDIS_PUBSUB_PUBLISH_TOTAL.labels(result="ok")
REDIS_PUBSUB_PUBLISH_TOTAL.labels(result="error")


def now_ms() -> int:
    """Wall-clock epoch milliseconds, comparable across instances."""
    return int(time.time() * 1000)


def observe_broadcast_latency(event: dict[str, Any]) -> None:
    """Record receive → fanout latency for a ``message.new`` with ``server_ts``."""
    if event.get("type") != "message.new":
        return
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return
    server_ts = cast(dict[str, Any], payload).get("server_ts")
    if not isinstance(server_ts, int):
        return
    # Clamp: small clock differences between hosts must not go negative.
    elapsed = max(time.time() - server_ts / 1000, 0.0)
    MESSAGE_BROADCAST_LATENCY_SECONDS.observe(elapsed)

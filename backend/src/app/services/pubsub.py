"""
Redis Pub/Sub fanout (S6.1).

Every WebSocket event is published to the Redis topic ``channel:{channel_id}``.
Each backend instance runs one ``RedisBus``. It subscribes to the topics of
channels that have at least one socket on *this* instance and hands every
event it receives to the local ``ConnectionManager``.

The publishing instance receives its own event back from Redis, so every
socket has exactly one delivery path regardless of which instance the
sender is connected to.

Tracing (S7.2): when ``publish`` runs inside a span, the W3C trace context is
added to the envelope under ``trace``, and every delivering instance opens a
``pubsub.deliver`` span under it, so one trace shows the send on instance A
and the fanout on instances A..N. Events published outside a span (typing,
presence leave) carry no context and produce no spans.
"""

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import redis.asyncio as aioredis
import structlog
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import SpanKind, StatusCode
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

from app.metrics import REDIS_PUBSUB_PUBLISH_TOTAL

logger = structlog.get_logger(__name__)
_tracer = trace.get_tracer(__name__)

Deliver = Callable[[uuid.UUID, dict[str, Any], uuid.UUID | None], Awaitable[None]]

TOPIC_PREFIX = "channel:"
# Subscribed at startup so the listener always has a live pubsub connection,
# even before any channel has a local socket.
_CONTROL_TOPIC = "chat-engine:control"

_RECONNECT_BACKOFF_START = 0.1
_RECONNECT_BACKOFF_MAX = 5.0
_POLL_TIMEOUT = 1.0

_REDIS_ERRORS = (RedisError, OSError)


def topic_for(channel_id: uuid.UUID) -> str:
    return f"{TOPIC_PREFIX}{channel_id}"


def _messaging_attributes(topic: str) -> dict[str, str]:
    return {"messaging.system": "redis", "messaging.destination.name": topic}


def _channel_from_topic(topic: str) -> uuid.UUID | None:
    if not topic.startswith(TOPIC_PREFIX):
        return None
    try:
        return uuid.UUID(topic.removeprefix(TOPIC_PREFIX))
    except ValueError:
        return None


class RedisBus:
    """One per process. Owns the Redis publish client and the subscriber."""

    def __init__(
        self,
        redis_url: str,
        deliver: Deliver,
        *,
        subscribe_timeout: float = 2.0,
    ) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(  # pyright: ignore[reportUnknownMemberType]
            redis_url, decode_responses=True
        )
        self._pubsub: PubSub = self._redis.pubsub()  # pyright: ignore[reportUnknownMemberType]
        self._deliver = deliver
        self._subscribe_timeout = subscribe_timeout
        # Topics this instance should be subscribed to. Tracked here because
        # redis-py only records a channel after SUBSCRIBE was sent
        # successfully, so subscriptions attempted while Redis is down would
        # otherwise be lost on reconnect.
        self._wanted: set[str] = set()
        self._confirmations: dict[str, asyncio.Event] = {}
        self._connected = False
        self._task: asyncio.Task[None] | None = None

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        await self._connect()
        self._task = asyncio.create_task(self._listen(), name="redis-bus-listener")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        with contextlib.suppress(*_REDIS_ERRORS):
            await self._pubsub.aclose()
        with contextlib.suppress(*_REDIS_ERRORS):
            await self._redis.aclose()

    # -- publish / subscribe ------------------------------------------------

    async def publish(
        self,
        channel_id: uuid.UUID,
        payload: dict[str, Any],
        exclude_user_id: uuid.UUID | None = None,
    ) -> None:
        topic = topic_for(channel_id)
        envelope: dict[str, Any] = {
            "payload": payload,
            "exclude_user_id": str(exclude_user_id) if exclude_user_id else None,
        }
        if not trace.get_current_span().get_span_context().is_valid:
            await self._send(topic, envelope, channel_id, payload, exclude_user_id)
            return
        with _tracer.start_as_current_span(
            "pubsub.publish",
            kind=SpanKind.PRODUCER,
            attributes=_messaging_attributes(topic),
        ):
            carrier: dict[str, str] = {}
            inject(carrier)
            envelope["trace"] = carrier
            await self._send(topic, envelope, channel_id, payload, exclude_user_id)

    async def _send(
        self,
        topic: str,
        envelope: dict[str, Any],
        channel_id: uuid.UUID,
        payload: dict[str, Any],
        exclude_user_id: uuid.UUID | None,
    ) -> None:
        try:
            await self._redis.publish(  # pyright: ignore[reportUnknownMemberType]
                topic, json.dumps(envelope, default=str)
            )
            REDIS_PUBSUB_PUBLISH_TOTAL.labels(result="ok").inc()
        except _REDIS_ERRORS as exc:
            REDIS_PUBSUB_PUBLISH_TOTAL.labels(result="error").inc()
            trace.get_current_span().set_status(StatusCode.ERROR, "publish failed")
            # Degrade to single-instance delivery rather than dropping the event.
            logger.warning(
                "pubsub_publish_failed_local_fallback",
                channel_id=str(channel_id),
                error=str(exc),
            )
            await self._deliver(channel_id, payload, exclude_user_id)

    async def subscribe(self, channel_id: uuid.UUID) -> None:
        """Subscribe and wait for Redis to confirm, so no early event is missed."""
        topic = topic_for(channel_id)
        self._wanted.add(topic)
        if not self._connected:
            return  # the listener subscribes to everything in _wanted on reconnect

        confirmed = asyncio.Event()
        self._confirmations[topic] = confirmed
        try:
            await self._pubsub.subscribe(topic)  # pyright: ignore[reportUnknownMemberType]
            await asyncio.wait_for(confirmed.wait(), self._subscribe_timeout)
        except (*_REDIS_ERRORS, TimeoutError) as exc:
            logger.warning(
                "pubsub_subscribe_failed", channel_id=str(channel_id), error=str(exc)
            )
        finally:
            self._confirmations.pop(topic, None)

    async def unsubscribe(self, channel_id: uuid.UUID) -> None:
        topic = topic_for(channel_id)
        self._wanted.discard(topic)
        if not self._connected:
            return
        try:
            await self._pubsub.unsubscribe(topic)  # pyright: ignore[reportUnknownMemberType]
        except _REDIS_ERRORS as exc:
            logger.warning(
                "pubsub_unsubscribe_failed", channel_id=str(channel_id), error=str(exc)
            )

    def is_subscribed(self, channel_id: uuid.UUID) -> bool:
        return topic_for(channel_id) in self._wanted

    # -- listener -----------------------------------------------------------

    async def _connect(self) -> bool:
        try:
            await self._pubsub.subscribe(_CONTROL_TOPIC, *self._wanted)  # pyright: ignore[reportUnknownMemberType]
        except _REDIS_ERRORS as exc:
            logger.warning("pubsub_connect_failed", error=str(exc))
            self._connected = False
            return False
        self._connected = True
        logger.info("pubsub_connected", topics=len(self._wanted))
        return True

    async def _listen(self) -> None:
        backoff = _RECONNECT_BACKOFF_START
        while True:
            if not self._connected:
                if not await self._connect():
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, _RECONNECT_BACKOFF_MAX)
                    continue
                backoff = _RECONNECT_BACKOFF_START
            try:
                message: Any = await self._pubsub.get_message(  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
                    timeout=_POLL_TIMEOUT
                )
            except _REDIS_ERRORS as exc:
                logger.warning("pubsub_listener_error", error=str(exc))
                self._connected = False
                continue
            if message is not None:
                await self._dispatch(cast(dict[str, Any], message))

    async def _dispatch(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        topic = str(message.get("channel", ""))

        if kind == "subscribe":
            confirmed = self._confirmations.get(topic)
            if confirmed is not None:
                confirmed.set()
            return
        if kind != "message":
            return

        channel_id = _channel_from_topic(topic)
        if channel_id is None:
            return
        try:
            envelope = json.loads(message["data"])
            payload: dict[str, Any] = envelope["payload"]
            exclude = envelope.get("exclude_user_id")
            exclude_user_id = uuid.UUID(exclude) if exclude else None
            carrier: Any = envelope.get("trace")
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning("pubsub_bad_envelope", topic=topic, error=str(exc))
            return

        parent = None
        if isinstance(carrier, dict):
            parent = extract(cast(dict[str, str], carrier))
        traced = (
            parent is not None
            and trace.get_current_span(parent).get_span_context().is_valid
        )
        if not traced:
            await self._deliver_safely(channel_id, payload, exclude_user_id)
            return
        with _tracer.start_as_current_span(
            "pubsub.deliver",
            context=parent,
            kind=SpanKind.CONSUMER,
            attributes=_messaging_attributes(topic),
        ):
            await self._deliver_safely(channel_id, payload, exclude_user_id)

    async def _deliver_safely(
        self,
        channel_id: uuid.UUID,
        payload: dict[str, Any],
        exclude_user_id: uuid.UUID | None,
    ) -> None:
        try:
            await self._deliver(channel_id, payload, exclude_user_id)
        except Exception as exc:
            # Never let one bad delivery kill the listener for every channel.
            logger.exception("pubsub_deliver_failed", channel_id=str(channel_id))
            span = trace.get_current_span()
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, "deliver failed")


# ---------------------------------------------------------------------------
# Process-wide bus, installed by the app lifespan (see main.py).
# ---------------------------------------------------------------------------

_bus: RedisBus | None = None


def set_bus(bus: RedisBus | None) -> None:
    global _bus
    _bus = bus


async def publish(
    channel_id: uuid.UUID,
    payload: dict[str, Any],
    exclude_user_id: uuid.UUID | None = None,
) -> None:
    """Fan *payload* out to every socket in *channel_id*, on every instance."""
    if _bus is None:
        logger.error("pubsub_bus_not_started", channel_id=str(channel_id))
        return
    await _bus.publish(channel_id, payload, exclude_user_id)

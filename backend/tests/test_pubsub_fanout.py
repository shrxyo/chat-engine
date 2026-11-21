"""
Cross-instance fanout via Redis Pub/Sub (S6.1).

Each "instance" is a ConnectionManager + RedisBus pair, exactly what one
backend process runs. Two instances share the real Redis from
docker-compose, so these tests prove that a message published on one
process reaches sockets held by another.

Requires: `docker compose up -d redis`.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings
from app.services.connection_manager import ConnectionManager
from app.services.pubsub import RedisBus, topic_for

REDIS_URL = get_settings().REDIS_URL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeWebSocket:
    """Stands in for starlette's WebSocket: records what is sent to it."""

    def __init__(self, send_delay: float = 0.0) -> None:
        self.sent: list[dict[str, Any]] = []
        self.closed_code: int | None = None
        self._send_delay = send_delay

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._send_delay:
            await asyncio.sleep(self._send_delay)
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code


class Instance:
    def __init__(self, redis_url: str, send_timeout: float = 2.0) -> None:
        self.manager = ConnectionManager(send_timeout=send_timeout)
        self.bus = RedisBus(redis_url, deliver=self.manager.broadcast_to_channel)

    async def start(self) -> None:
        await self.bus.start()
        self.manager.attach_subscriber(self.bus)

    async def stop(self) -> None:
        self.manager.attach_subscriber(None)
        await self.bus.stop()


@asynccontextmanager
async def instances(
    count: int, redis_url: str = REDIS_URL, send_timeout: float = 2.0
) -> AsyncIterator[list[Instance]]:
    # Built inside the test (not a fixture) so Redis connections live on the
    # test's own event loop.
    started = [Instance(redis_url, send_timeout) for _ in range(count)]
    for inst in started:
        await inst.start()
    try:
        yield started
    finally:
        for inst in started:
            await inst.stop()


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError("condition not met before timeout")
        await asyncio.sleep(0.01)


def event(n: int) -> dict[str, Any]:
    return {"type": "message.new", "payload": {"n": n}}


async def numsub(channel_id: uuid.UUID) -> int:
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        result: list[tuple[str, int]] = await client.pubsub_numsub(  # pyright: ignore[reportUnknownMemberType]
            topic_for(channel_id)
        )
        return int(result[0][1])
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_message_published_on_one_instance_reaches_another() -> None:
    channel_id = uuid.uuid4()
    async with instances(2) as (a, b):
        ws_a, ws_b = FakeWebSocket(), FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws_a)  # type: ignore[arg-type]
        await b.manager.connect(uuid.uuid4(), channel_id, ws_b)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, event(1))

        await wait_until(lambda: len(ws_a.sent) == 1 and len(ws_b.sent) == 1)
        assert ws_b.sent == [event(1)]


async def test_publishing_instance_delivers_exactly_once() -> None:
    # Delivery comes only from the Redis echo, never an extra local send.
    channel_id = uuid.uuid4()
    async with instances(1) as (a,):
        ws = FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, event(1))
        await a.bus.publish(channel_id, event(2))

        await wait_until(lambda: len(ws.sent) >= 2)
        await asyncio.sleep(0.05)
        assert ws.sent == [event(1), event(2)]


async def test_exclude_user_id_applies_on_every_instance() -> None:
    channel_id = uuid.uuid4()
    sender = uuid.uuid4()
    async with instances(2) as (a, b):
        ws_sender_on_b = FakeWebSocket()
        ws_other_on_b = FakeWebSocket()
        await b.manager.connect(sender, channel_id, ws_sender_on_b)  # type: ignore[arg-type]
        await b.manager.connect(uuid.uuid4(), channel_id, ws_other_on_b)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, event(1), exclude_user_id=sender)

        await wait_until(lambda: len(ws_other_on_b.sent) == 1)
        assert ws_sender_on_b.sent == []


async def test_instance_unsubscribes_when_last_local_socket_leaves() -> None:
    channel_id = uuid.uuid4()
    async with instances(2) as (a, b):
        user_1, user_2 = uuid.uuid4(), uuid.uuid4()
        ws_1, ws_2 = FakeWebSocket(), FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, FakeWebSocket())  # type: ignore[arg-type]
        await b.manager.connect(user_1, channel_id, ws_1)  # type: ignore[arg-type]
        await b.manager.connect(user_2, channel_id, ws_2)  # type: ignore[arg-type]
        assert await numsub(channel_id) == 2

        await b.manager.disconnect(user_1, channel_id, ws_1)  # type: ignore[arg-type]
        assert await numsub(channel_id) == 2  # user_2 still on b

        await b.manager.disconnect(user_2, channel_id, ws_2)  # type: ignore[arg-type]
        await wait_until(lambda: not b.bus.is_subscribed(channel_id))
        assert await numsub(channel_id) == 1  # only a remains


async def test_disconnect_ignores_a_socket_that_was_replaced() -> None:
    # Same user opens a second tab: closing the old tab must not drop the new one.
    channel_id = uuid.uuid4()
    user = uuid.uuid4()
    async with instances(1) as (a,):
        old_tab, new_tab = FakeWebSocket(), FakeWebSocket()
        await a.manager.connect(user, channel_id, old_tab)  # type: ignore[arg-type]
        await a.manager.connect(user, channel_id, new_tab)  # type: ignore[arg-type]

        await a.manager.disconnect(user, channel_id, old_tab)  # type: ignore[arg-type]
        await a.bus.publish(channel_id, event(1))

        await wait_until(lambda: len(new_tab.sent) == 1)
        assert old_tab.sent == []


async def test_slow_socket_is_evicted_without_delaying_others() -> None:
    channel_id = uuid.uuid4()
    async with instances(1, send_timeout=0.2) as (a,):
        slow, fast = FakeWebSocket(send_delay=5.0), FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, slow)  # type: ignore[arg-type]
        await a.manager.connect(uuid.uuid4(), channel_id, fast)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, event(1))

        await wait_until(lambda: len(fast.sent) == 1, timeout=0.5)
        await wait_until(lambda: slow.closed_code == 1013)
        assert a.manager.local_connection_count(channel_id) == 1


async def test_publish_falls_back_to_local_delivery_when_redis_is_down() -> None:
    channel_id = uuid.uuid4()
    async with instances(1, redis_url="redis://127.0.0.1:1/0") as (a,):
        ws = FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]

        await a.bus.publish(channel_id, event(1))

        assert ws.sent == [event(1)]


async def test_listener_resubscribes_after_redis_drops_the_connection() -> None:
    channel_id = uuid.uuid4()
    async with instances(1) as (a,):
        ws = FakeWebSocket()
        await a.manager.connect(uuid.uuid4(), channel_id, ws)  # type: ignore[arg-type]
        assert await numsub(channel_id) == 1

        admin = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            await admin.client_kill_filter(_type="pubsub")  # pyright: ignore[reportUnknownMemberType]
        finally:
            await admin.aclose()

        # Pub/Sub is at-most-once: wait for the resubscribe before publishing.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while await numsub(channel_id) != 1:
            assert loop.time() < deadline, "listener never resubscribed"
            await asyncio.sleep(0.05)

        await a.bus.publish(channel_id, event(1))
        await wait_until(lambda: ws.sent == [event(1)])

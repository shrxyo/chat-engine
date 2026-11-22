"""
Presence via Redis (S4.2).

Store-level tests run two ``PresenceStore`` instances against the real Redis
from docker-compose, standing in for two backend replicas. Each test uses its
own key prefix so the dev stack's sweepers (same Redis) never touch its keys.

Requires: `docker compose up -d redis` (and postgres for the WebSocket tests).
"""

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
import redis.asyncio as aioredis
from starlette.testclient import TestClient

from app.config import get_settings
from app.services.presence import PresenceConnection, PresenceStore
from tests.conftest import make_token
from tests.factories import ChannelFactory, ChannelMembershipFactory, UserFactory
from tests.test_ws import _make_app  # pyright: ignore[reportPrivateUsage]

REDIS_URL = get_settings().REDIS_URL

# Short TTL so expiry tests run in well under a second.
TTL = 0.3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def stores(
    count: int,
    *,
    ttl: float = TTL,
    sweep_interval: float = 60.0,
    redis_url: str = REDIS_URL,
    offline: list[tuple[uuid.UUID, uuid.UUID]] | None = None,
) -> AsyncIterator[list[PresenceStore]]:
    """*count* stores sharing one key prefix, like replicas sharing Redis."""
    prefix = f"test-presence-{uuid.uuid4()}"

    async def on_offline(channel_id: uuid.UUID, user_id: uuid.UUID) -> None:
        if offline is not None:
            offline.append((channel_id, user_id))

    started = [
        PresenceStore(
            redis_url,
            ttl=ttl,
            sweep_interval=sweep_interval,
            on_offline=on_offline,
            key_prefix=prefix,
        )
        for _ in range(count)
    ]
    for store in started:
        await store.start()
    try:
        yield started
    finally:
        for store in started:
            await store.stop()
        if redis_url == REDIS_URL:
            client = aioredis.from_url(REDIS_URL, decode_responses=True)
            keys: list[str] = await client.keys(f"{prefix}:*")  # pyright: ignore[reportUnknownMemberType]
            if keys:
                await client.delete(*keys)
            await client.aclose()


def ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


# ---------------------------------------------------------------------------
# Store: join / leave / snapshot across instances
# ---------------------------------------------------------------------------


async def test_first_connection_brings_user_online_on_any_instance() -> None:
    channel, alice, bob = ids(3)
    async with stores(2) as (a, b):
        assert await a.touch(channel, alice, uuid.uuid4()) is True
        # Alice's second tab, on another replica: already online, no join.
        assert await b.touch(channel, alice, uuid.uuid4()) is False
        assert await b.touch(channel, bob, uuid.uuid4()) is True

        assert sorted(await a.online(channel)) == sorted([alice, bob])
        assert sorted(await b.online(channel)) == sorted([alice, bob])


async def test_user_goes_offline_only_when_last_connection_leaves() -> None:
    channel, alice = ids(2)
    tab1, tab2 = ids(2)
    async with stores(2) as (a, b):
        await a.touch(channel, alice, tab1)
        await b.touch(channel, alice, tab2)

        assert await a.leave(channel, alice, tab1) is False
        assert await b.online(channel) == [alice]
        assert await b.leave(channel, alice, tab2) is True
        assert await a.online(channel) == []
        # Leaving again (or a connection that never joined) is a no-op.
        assert await a.leave(channel, alice, tab1) is False
        assert await a.channels() == []


async def test_user_key_has_ttl() -> None:
    channel, alice = ids(2)
    async with stores(1, ttl=30) as (a,):
        await a.touch(channel, alice, uuid.uuid4())
        client = aioredis.from_url(REDIS_URL, decode_responses=True)
        try:
            pttl = await client.pttl(a.user_key(alice))  # pyright: ignore[reportUnknownMemberType]
        finally:
            await client.aclose()
        assert 29_000 < pttl <= 30_000


# ---------------------------------------------------------------------------
# Store: TTL expiry
# ---------------------------------------------------------------------------


async def test_expired_connection_is_swept_exactly_once() -> None:
    channel, alice, bob = ids(3)
    async with stores(2) as (a, b):
        await a.touch(channel, alice, uuid.uuid4())
        await a.touch(channel, bob, uuid.uuid4())
        await asyncio.sleep(TTL / 2)
        await a.touch(channel, bob, uuid.uuid4())  # bob stays alive
        await asyncio.sleep(TTL / 2 + 0.05)

        # Both replicas sweep at once; only one may report alice offline.
        swept = await asyncio.gather(a.sweep(), b.sweep())
        assert sorted(swept, key=len) == [[], [(channel, alice)]]
        assert await a.online(channel) == [bob]


async def test_refresh_keeps_connection_alive() -> None:
    channel, alice = ids(2)
    conn = uuid.uuid4()
    async with stores(1) as (a,):
        await a.touch(channel, alice, conn)
        for _ in range(3):
            await asyncio.sleep(TTL / 2)
            assert await a.touch(channel, alice, conn) is False
        assert await a.sweep() == []
        assert await a.online(channel) == [alice]


async def test_leave_after_expiry_does_not_repeat_the_leave() -> None:
    channel, alice = ids(2)
    conn = uuid.uuid4()
    async with stores(1) as (a,):
        await a.touch(channel, alice, conn)
        await asyncio.sleep(TTL + 0.05)
        assert await a.sweep() == [(channel, alice)]
        assert await a.leave(channel, alice, conn) is False


async def test_stale_connection_does_not_cause_a_late_leave() -> None:
    """A crashed tab's entry must not mark the user offline after a reconnect."""
    channel, alice = ids(2)
    crashed, fresh = ids(2)
    async with stores(1) as (a,):
        await a.touch(channel, alice, crashed)
        await asyncio.sleep(TTL + 0.05)
        # Reconnects before any sweep: offline again, so this is a join.
        assert await a.touch(channel, alice, fresh) is True
        assert await a.sweep() == []
        assert await a.online(channel) == [alice]
        # Closing the fresh socket is the one leave; nothing left to sweep.
        assert await a.leave(channel, alice, fresh) is True
        await asyncio.sleep(TTL + 0.05)
        assert await a.sweep() == []


async def test_touch_after_expiry_rejoins() -> None:
    """A socket that stopped pinging, then speaks again, comes back online."""
    channel, alice = ids(2)
    conn = uuid.uuid4()
    async with stores(1) as (a,):
        await a.touch(channel, alice, conn)
        await asyncio.sleep(TTL + 0.05)
        assert await a.sweep() == [(channel, alice)]
        assert await a.touch(channel, alice, conn) is True


async def test_sweeper_reports_offline_users_in_background() -> None:
    channel, alice = ids(2)
    offline: list[tuple[uuid.UUID, uuid.UUID]] = []
    async with stores(2, sweep_interval=0.05, offline=offline) as (a, _b):
        await a.touch(channel, alice, uuid.uuid4())
        await asyncio.sleep(TTL + 0.3)
        assert offline == [(channel, alice)]
        assert await a.channels() == []


# ---------------------------------------------------------------------------
# PresenceConnection: throttled refresh, Redis failures
# ---------------------------------------------------------------------------


async def test_connection_refresh_is_throttled() -> None:
    channel, alice = ids(2)
    async with stores(1, ttl=0.6) as (a,):
        conn = PresenceConnection(a, channel, alice)
        assert await conn.join() is True
        # Within ttl/3 of the last touch: no Redis call, entry not extended.
        assert await conn.refresh() is False
        await asyncio.sleep(0.25)
        assert await conn.refresh() is False  # touched, already online
        await asyncio.sleep(0.45)
        # Expiry is 0.6s after the refresh at 0.25s, so still online.
        assert await a.sweep() == []
        assert await conn.leave() is True


async def test_connection_survives_redis_outage() -> None:
    channel, alice = ids(2)
    store = PresenceStore(
        "redis://127.0.0.1:1/0", ttl=TTL, sweep_interval=60, key_prefix="unused"
    )
    conn = PresenceConnection(store, channel, alice)
    # Unknown state: report changes so join/leave still go out.
    assert await conn.join() is True
    assert await conn.online() == [alice]
    assert await conn.leave() is True
    await store.stop()


async def test_connection_without_store_degrades_to_join_leave() -> None:
    channel, alice = ids(2)
    conn = PresenceConnection(None, channel, alice)
    assert await conn.join() is True
    assert await conn.refresh() is False
    assert await conn.online() == [alice]
    assert await conn.leave() is True


# ---------------------------------------------------------------------------
# WebSocket: snapshot, join, leave, ping
# ---------------------------------------------------------------------------


async def _two_members(db_session: Any) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    alice, bob = UserFactory.build(), UserFactory.build()
    channel = ChannelFactory.build(created_by=alice.id)
    db_session.add_all([alice, bob])
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add_all(
        [
            ChannelMembershipFactory.build(user_id=alice.id, channel_id=channel.id),
            ChannelMembershipFactory.build(user_id=bob.id, channel_id=channel.id),
        ]
    )
    await db_session.commit()
    return channel.id, alice.id, bob.id


async def test_snapshot_join_and_leave_over_websocket(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel_id, alice, bob = await _two_members(db_session)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel_id}?token={make_token(alice)}") as ws_a,
    ):
        snapshot = ws_a.receive_json()
        assert snapshot == {
            "type": "presence.snapshot",
            "payload": {"channel_id": str(channel_id), "online_user_ids": [str(alice)]},
        }

        with client.websocket_connect(
            f"/ws/{channel_id}?token={make_token(bob)}"
        ) as ws_b:
            snapshot_b = ws_b.receive_json()
            assert snapshot_b["type"] == "presence.snapshot"
            assert sorted(snapshot_b["payload"]["online_user_ids"]) == sorted(
                [str(alice), str(bob)]
            )
            joined = ws_a.receive_json()
            assert joined["type"] == "presence.join"
            assert joined["payload"]["user_id"] == str(bob)
            # Make sure bob's handler is in its receive loop before closing.
            ws_b.send_json({"type": "bogus"})
            assert ws_b.receive_json()["type"] == "error"

        left = ws_a.receive_json()
        assert left["type"] == "presence.leave"
        assert left["payload"]["user_id"] == str(bob)


async def test_ping_is_accepted_silently(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    channel_id, alice, _bob = await _two_members(db_session)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel_id}?token={make_token(alice)}") as ws,
    ):
        assert ws.receive_json()["type"] == "presence.snapshot"
        started = time.monotonic()
        ws.send_json({"type": "ping"})
        ws.send_json({"type": "bogus"})
        # The ping produced no reply: the next frame answers the bogus event.
        reply = ws.receive_json()
        assert reply["type"] == "error"
        assert "bogus" in reply["payload"]["message"]
        assert time.monotonic() - started < 2


async def test_sweeper_survives_redis_errors_and_failing_callbacks() -> None:
    channel, alice, bob = ids(3)
    calls: list[uuid.UUID] = []

    async def flaky(_channel: uuid.UUID, user_id: uuid.UUID) -> None:
        calls.append(user_id)
        raise RuntimeError("publish failed")

    # Redis unreachable: the loop logs and keeps going.
    down = PresenceStore(
        "redis://127.0.0.1:1/0", ttl=TTL, sweep_interval=0.02, key_prefix="unused"
    )
    await down.start()
    await asyncio.sleep(0.1)
    assert down._task is not None and not down._task.done()  # pyright: ignore[reportPrivateUsage]
    await down.stop()

    async with stores(1) as (a,):
        for on_offline in (flaky, None):
            sweeper = PresenceStore(
                REDIS_URL,
                ttl=TTL,
                sweep_interval=0.05,
                on_offline=on_offline,
                key_prefix=a._prefix,  # pyright: ignore[reportPrivateUsage]
            )
            await a.touch(channel, alice, uuid.uuid4())
            await a.touch(channel, bob, uuid.uuid4())
            await sweeper.start()
            await asyncio.sleep(TTL + 0.2)
            assert sweeper._task is not None and not sweeper._task.done()  # pyright: ignore[reportPrivateUsage]
            await sweeper.stop()
            assert await a.online(channel) == []
    # A failing callback doesn't stop the others in the same sweep.
    assert sorted(calls) == sorted([alice, bob])

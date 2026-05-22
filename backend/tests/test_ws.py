"""
WebSocket gateway tests.

Uses starlette.testclient.TestClient (sync) for WebSocket connections.
Each async test:
  1. Inserts fixture data via the async `db_session`.
  2. Monkeypatches `app.routers.ws.AsyncSessionLocal` → TestSessionLocal so
     the WS handler queries the same test database.
  3. Mocks `app.routers.ws.publish` to a no-op (avoids Redis in CI).
  4. Opens a sync TestClient and exercises the WebSocket.
"""

import threading
import time
import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.routers.ws as ws_module
from app.database import get_session
from app.main import create_app
from app.models.message import Message
from tests.conftest import TEST_DATABASE_URL, TestSessionLocal, make_token
from tests.factories import (
    ChannelFactory,
    ChannelMembershipFactory,
    MessageFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _noop_publish(channel_id: uuid.UUID, payload: dict[str, Any]) -> None:  # noqa: ARG001
    pass


def _make_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    Return a FastAPI app wired to the test database.

    A fresh engine is created so the WS handler's asyncpg connections are
    born in the TestClient's event loop (not the pytest session loop).
    Sharing test_engine across loops causes "Future attached to a different
    loop" errors during teardown.

    Patches:
    - `app.routers.ws.AsyncSessionLocal` → fresh session factory pointing at chatdb_test
    - `app.routers.ws.publish` → no-op coroutine
    """
    ws_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
    WsSessionLocal = async_sessionmaker(
        ws_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(ws_module, "AsyncSessionLocal", WsSessionLocal)
    monkeypatch.setattr(ws_module, "publish", _noop_publish)

    application = create_app()

    async def _override_session():  # type: ignore[return]
        async with TestSessionLocal() as session:
            yield session

    application.dependency_overrides[get_session] = _override_session
    return application


# ---------------------------------------------------------------------------
# Test: successful connect + presence.join broadcast to other member
# ---------------------------------------------------------------------------


async def test_presence_join_broadcast(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_a = UserFactory.build()
    user_b = UserFactory.build()
    channel = ChannelFactory.build(created_by=user_a.id)
    db_session.add_all([user_a, user_b])
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add_all(
        [
            ChannelMembershipFactory.build(user_id=user_a.id, channel_id=channel.id),
            ChannelMembershipFactory.build(user_id=user_b.id, channel_id=channel.id),
        ]
    )
    await db_session.commit()

    token_a = make_token(user_a.id)
    token_b = make_token(user_b.id)
    application = _make_app(monkeypatch)

    received_by_a: list[dict[str, Any]] = []

    def _listen_a(client: TestClient) -> None:
        with client.websocket_connect(f"/ws/{channel.id}?token={token_a}") as ws_a:
            # Receive the presence.join that B's connect triggers
            msg = ws_a.receive_json()
            received_by_a.append(msg)

    with TestClient(application) as client:
        t = threading.Thread(target=_listen_a, args=(client,), daemon=True)
        t.start()
        time.sleep(0.15)  # give user A time to connect first

        with client.websocket_connect(f"/ws/{channel.id}?token={token_b}"):
            t.join(timeout=3)

    assert len(received_by_a) == 1
    assert received_by_a[0]["type"] == "presence.join"
    assert received_by_a[0]["payload"]["user_id"] == str(user_b.id)


# ---------------------------------------------------------------------------
# Test: message.new persists to DB and broadcasts
# ---------------------------------------------------------------------------


async def test_message_new_persists_and_broadcasts(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
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

    token = make_token(user.id)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={token}") as ws,
    ):
        ws.send_json({"type": "message.new", "payload": {"content": "hello ws"}})
        broadcast = ws.receive_json()

    assert broadcast["type"] == "message.new"
    assert broadcast["payload"]["content"] == "hello ws"
    assert broadcast["payload"]["channel_id"] == str(channel.id)
    assert broadcast["payload"]["user_id"] == str(user.id)

    # Verify persisted to DB
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(Message).where(Message.channel_id == channel.id)
        )
        rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].content == "hello ws"
    assert rows[0].deleted_at is None


# ---------------------------------------------------------------------------
# Test: message.edit updates DB
# ---------------------------------------------------------------------------


async def test_message_edit_updates_db(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = UserFactory.build()
    channel = ChannelFactory.build(created_by=user.id)
    message = MessageFactory.build(channel_id=channel.id, user_id=user.id)
    db_session.add(user)
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add(
        ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    )
    db_session.add(message)
    await db_session.commit()

    token = make_token(user.id)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={token}") as ws,
    ):
        ws.send_json(
            {
                "type": "message.edit",
                "payload": {
                    "message_id": str(message.id),
                    "content": "edited content",
                },
            }
        )
        broadcast = ws.receive_json()

    assert broadcast["type"] == "message.edit"
    assert broadcast["payload"]["content"] == "edited content"
    assert broadcast["payload"]["id"] == str(message.id)

    async with TestSessionLocal() as session:
        updated = await session.get(Message, message.id)
    assert updated is not None
    assert updated.content == "edited content"
    assert updated.edited_at is not None


# ---------------------------------------------------------------------------
# Test: message.delete soft-deletes
# ---------------------------------------------------------------------------


async def test_message_delete_soft_deletes(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = UserFactory.build()
    channel = ChannelFactory.build(created_by=user.id)
    message = MessageFactory.build(channel_id=channel.id, user_id=user.id)
    db_session.add(user)
    await db_session.flush()
    db_session.add(channel)
    await db_session.flush()
    db_session.add(
        ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    )
    db_session.add(message)
    await db_session.commit()

    token = make_token(user.id)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={token}") as ws,
    ):
        ws.send_json(
            {
                "type": "message.delete",
                "payload": {"message_id": str(message.id)},
            }
        )
        broadcast = ws.receive_json()

    assert broadcast["type"] == "message.delete"
    assert broadcast["payload"]["message_id"] == str(message.id)

    async with TestSessionLocal() as session:
        deleted = await session.get(Message, message.id)
    assert deleted is not None
    assert deleted.deleted_at is not None


# ---------------------------------------------------------------------------
# Test: typing events broadcast without DB write
# ---------------------------------------------------------------------------


async def test_typing_events_no_db_write(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
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

    token = make_token(user.id)
    application = _make_app(monkeypatch)

    with (
        TestClient(application) as client,
        client.websocket_connect(f"/ws/{channel.id}?token={token}") as ws,
    ):
        # Send typing events — they are excluded from the sender's own receive,
        # so follow up with message.new which DOES echo back.
        ws.send_json({"type": "typing.start", "payload": {}})
        ws.send_json({"type": "typing.stop", "payload": {}})
        ws.send_json({"type": "message.new", "payload": {"content": "ping"}})
        broadcast = ws.receive_json()

    # The first receive is the message.new echo (typing events are not sent back to sender)
    assert broadcast["type"] == "message.new"

    # No extra rows from typing events
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(Message).where(Message.channel_id == channel.id)
        )
        rows = result.scalars().all()
    assert len(rows) == 1  # only the message.new row


# ---------------------------------------------------------------------------
# Test: invalid token rejected with close code 4001
# ---------------------------------------------------------------------------


async def test_invalid_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # JWT is rejected before any DB query; no rows need to exist.
    application = _make_app(monkeypatch)
    channel_id = uuid.uuid4()

    with (
        TestClient(application) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/{channel_id}?token=not-a-valid-jwt"),
    ):
        pass  # server closes before we can do anything

    assert exc_info.value.code == 4001


# ---------------------------------------------------------------------------
# Test: missing token rejected with close code 4001
# ---------------------------------------------------------------------------


async def test_missing_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Token query-param absent; rejected before any DB query.
    application = _make_app(monkeypatch)
    channel_id = uuid.uuid4()

    with (
        TestClient(application) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/{channel_id}"),
    ):
        pass

    assert exc_info.value.code == 4001


# ---------------------------------------------------------------------------
# Test: non-member rejected with close code 4001
# ---------------------------------------------------------------------------


async def test_non_member_rejected(
    db_session: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = UserFactory.build()
    db_session.add(user)
    # Deliberately do NOT create the channel or any ChannelMembership.
    # session.get(ChannelMembership, ...) will return None → close 4001.
    await db_session.commit()

    token = make_token(user.id)
    application = _make_app(monkeypatch)
    channel_id = uuid.uuid4()

    with (
        TestClient(application) as client,
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect(f"/ws/{channel_id}?token={token}"),
    ):
        pass

    assert exc_info.value.code == 4001

"""Tests for /api/channels/{channel_id}/messages and /api/messages/* endpoints."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MemberRole
from tests.conftest import auth_header
from tests.factories import (
    ChannelFactory,
    ChannelMembershipFactory,
    MessageFactory,
    UserFactory,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed(
    db_session: AsyncSession,
    *,
    role: MemberRole = MemberRole.member,
    message_count: int = 0,
) -> tuple:
    """Return (user, channel, messages_list)."""
    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()

    channel = ChannelFactory.build(created_by=user.id)
    db_session.add(channel)
    await db_session.flush()

    membership = ChannelMembershipFactory.build(
        user_id=user.id, channel_id=channel.id, role=role
    )
    db_session.add(membership)

    messages = []
    for _ in range(message_count):
        msg = MessageFactory.build(channel_id=channel.id, user_id=user.id)
        db_session.add(msg)
        messages.append(msg)

    await db_session.commit()
    return user, channel, messages


# ---------------------------------------------------------------------------
# GET /api/channels/{channel_id}/messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_messages_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed(db_session)

    response = await client.get(
        f"/api/channels/{channel.id}/messages", headers=auth_header(user.id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["messages"] == []
    assert body["has_more"] is False


@pytest.mark.asyncio
async def test_list_messages_returns_non_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed(db_session)

    live_msg = MessageFactory.build(channel_id=channel.id, user_id=user.id)
    deleted_msg = MessageFactory.build(
        channel_id=channel.id,
        user_id=user.id,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(live_msg)
    db_session.add(deleted_msg)
    await db_session.commit()

    response = await client.get(
        f"/api/channels/{channel.id}/messages", headers=auth_header(user.id)
    )
    assert response.status_code == 200
    ids = [m["id"] for m in response.json()["messages"]]
    assert str(live_msg.id) in ids
    assert str(deleted_msg.id) not in ids


@pytest.mark.asyncio
async def test_list_messages_pagination_has_more(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed(db_session, message_count=55)

    response = await client.get(
        f"/api/channels/{channel.id}/messages?limit=50",
        headers=auth_header(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 50
    assert body["has_more"] is True


@pytest.mark.asyncio
async def test_list_messages_pagination_cursor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed(db_session, message_count=5)

    # First page: all 5
    r1 = await client.get(
        f"/api/channels/{channel.id}/messages?limit=3",
        headers=auth_header(user.id),
    )
    assert r1.status_code == 200
    first_page = r1.json()["messages"]
    assert len(first_page) == 3
    oldest_id = first_page[-1]["id"]

    # Second page: remaining 2, before the oldest from page 1
    r2 = await client.get(
        f"/api/channels/{channel.id}/messages?limit=3&before={oldest_id}",
        headers=auth_header(user.id),
    )
    assert r2.status_code == 200
    second_page = r2.json()["messages"]
    assert len(second_page) == 2
    assert r2.json()["has_more"] is False


@pytest.mark.asyncio
async def test_list_messages_403_not_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    outsider = UserFactory.build()
    db_session.add(outsider)
    await db_session.flush()

    channel = ChannelFactory.build(created_by=outsider.id)
    db_session.add(channel)
    await db_session.commit()

    response = await client.get(
        f"/api/channels/{channel.id}/messages", headers=auth_header(outsider.id)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_list_messages_401_no_token(client: AsyncClient) -> None:
    response = await client.get(f"/api/channels/{uuid.uuid4()}/messages")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/messages/{message_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_own_message(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed(db_session)
    msg = MessageFactory.build(channel_id=channel.id, user_id=user.id)
    db_session.add(msg)
    await db_session.commit()

    response = await client.delete(
        f"/api/messages/{msg.id}", headers=auth_header(user.id)
    )
    assert response.status_code == 204

    # Should no longer appear in message list
    list_r = await client.get(
        f"/api/channels/{channel.id}/messages", headers=auth_header(user.id)
    )
    assert all(m["id"] != str(msg.id) for m in list_r.json()["messages"])


@pytest.mark.asyncio
async def test_delete_other_users_message_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = UserFactory.build()
    other = UserFactory.build()
    db_session.add(owner)
    db_session.add(other)
    await db_session.flush()

    channel = ChannelFactory.build(created_by=owner.id)
    db_session.add(channel)
    await db_session.flush()

    owner_membership = ChannelMembershipFactory.build(
        user_id=owner.id, channel_id=channel.id
    )
    other_membership = ChannelMembershipFactory.build(
        user_id=other.id, channel_id=channel.id
    )
    msg = MessageFactory.build(channel_id=channel.id, user_id=owner.id)
    db_session.add(owner_membership)
    db_session.add(other_membership)
    db_session.add(msg)
    await db_session.commit()

    response = await client.delete(
        f"/api/messages/{msg.id}", headers=auth_header(other.id)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_message_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.delete(
        f"/api/messages/{uuid.uuid4()}", headers=auth_header(user.id)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_message_no_token(client: AsyncClient) -> None:
    response = await client.delete(f"/api/messages/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/messages/{message_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_own_message(client: AsyncClient, db_session: AsyncSession) -> None:
    user, channel, _ = await _seed(db_session)
    msg = MessageFactory.build(
        channel_id=channel.id, user_id=user.id, content="original"
    )
    db_session.add(msg)
    await db_session.commit()

    response = await client.patch(
        f"/api/messages/{msg.id}",
        json={"content": "edited"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "edited"
    assert data["edited_at"] is not None


@pytest.mark.asyncio
async def test_patch_other_users_message_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    owner = UserFactory.build()
    other = UserFactory.build()
    db_session.add(owner)
    db_session.add(other)
    await db_session.flush()

    channel = ChannelFactory.build(created_by=owner.id)
    db_session.add(channel)
    await db_session.flush()

    msg = MessageFactory.build(channel_id=channel.id, user_id=owner.id)
    db_session.add(msg)
    await db_session.commit()

    response = await client.patch(
        f"/api/messages/{msg.id}",
        json={"content": "hack"},
        headers=auth_header(other.id),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_patch_message_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.patch(
        f"/api/messages/{uuid.uuid4()}",
        json={"content": "hello"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patch_message_no_token(client: AsyncClient) -> None:
    response = await client.patch(
        f"/api/messages/{uuid.uuid4()}", json={"content": "x"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_deleted_message_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed(db_session)
    msg = MessageFactory.build(
        channel_id=channel.id,
        user_id=user.id,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(msg)
    await db_session.commit()

    response = await client.patch(
        f"/api/messages/{msg.id}",
        json={"content": "edit deleted"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 404

"""Tests for /api/channels/{channel_id}/messages and /api/messages/* endpoints."""

import uuid
from datetime import UTC, datetime, timedelta

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


async def _seed_timeline(
    db_session: AsyncSession, count: int, *, same_time: bool = False
) -> tuple:
    """(user, channel, messages oldest-first) with distinct created_at values.

    ids are random uuid4, so id order and time order disagree: anything that
    orders or cursors by id alone fails these tests.
    """
    user, channel, _ = await _seed(db_session)
    base = datetime(2026, 1, 1, 12, 0, 0)
    messages = []
    for i in range(count):
        created = base if same_time else base + timedelta(seconds=i)
        msg = MessageFactory.build(
            channel_id=channel.id, user_id=user.id, created_at=created
        )
        db_session.add(msg)
        messages.append(msg)
    await db_session.commit()
    if same_time:
        messages.sort(key=lambda m: m.id)  # ties break by id
    return user, channel, messages


def _ids(response) -> list[str]:  # noqa: ANN001
    return [m["id"] for m in response.json()["messages"]]


@pytest.mark.asyncio
async def test_list_messages_newest_first_by_created_at(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 8)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?limit=3", headers=auth_header(user.id)
    )
    assert r.status_code == 200
    assert _ids(r) == [str(m.id) for m in reversed(messages[-3:])]


@pytest.mark.asyncio
async def test_list_messages_before_pages_without_gaps_or_repeats(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 10)

    seen: list[str] = []
    url = f"/api/channels/{channel.id}/messages?limit=4"
    cursor = None
    while True:
        r = await client.get(
            url + (f"&before={cursor}" if cursor else ""), headers=auth_header(user.id)
        )
        assert r.status_code == 200
        seen += _ids(r)
        if not r.json()["has_more"]:
            break
        cursor = seen[-1]

    assert seen == [str(m.id) for m in reversed(messages)]


@pytest.mark.asyncio
async def test_list_messages_after_returns_newer_messages(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 6)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?after={messages[2].id}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 200
    # Same order as every other page: newest first.
    assert _ids(r) == [str(m.id) for m in reversed(messages[3:])]
    assert r.json()["has_more"] is False


@pytest.mark.asyncio
async def test_list_messages_after_latest_is_empty(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 3)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?after={messages[-1].id}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 200
    assert r.json() == {"messages": [], "has_more": False}


@pytest.mark.asyncio
async def test_list_messages_after_limit_takes_oldest_and_sets_has_more(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A gap bigger than limit: the page right after the cursor, has_more=True,
    so the client can page forward with after=<newest returned>."""
    user, channel, messages = await _seed_timeline(db_session, 10)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?after={messages[1].id}&limit=3",
        headers=auth_header(user.id),
    )
    assert r.status_code == 200
    assert _ids(r) == [str(m.id) for m in reversed(messages[2:5])]
    assert r.json()["has_more"] is True


@pytest.mark.asyncio
async def test_list_messages_after_skips_deleted_and_accepts_deleted_cursor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 5)
    now = datetime.now(UTC).replace(tzinfo=None)
    messages[1].deleted_at = now  # the cursor: deleted while client was away
    messages[3].deleted_at = now
    db_session.add_all([messages[1], messages[3]])
    await db_session.commit()

    r = await client.get(
        f"/api/channels/{channel.id}/messages?after={messages[1].id}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 200
    assert _ids(r) == [str(messages[4].id), str(messages[2].id)]


@pytest.mark.asyncio
async def test_list_messages_cursor_ties_broken_by_id(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 5, same_time=True)
    url = f"/api/channels/{channel.id}/messages"

    r_after = await client.get(
        f"{url}?after={messages[1].id}", headers=auth_header(user.id)
    )
    r_before = await client.get(
        f"{url}?before={messages[1].id}", headers=auth_header(user.id)
    )
    assert _ids(r_after) == [str(m.id) for m in reversed(messages[2:])]
    assert _ids(r_before) == [str(messages[0].id)]


@pytest.mark.asyncio
async def test_list_messages_before_and_after_together_422(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, messages = await _seed_timeline(db_session, 2)

    r = await client.get(
        f"/api/channels/{channel.id}/messages"
        f"?after={messages[0].id}&before={messages[1].id}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("param", ["after", "before"])
async def test_list_messages_unknown_cursor_400(
    client: AsyncClient, db_session: AsyncSession, param: str
) -> None:
    user, channel, _ = await _seed_timeline(db_session, 2)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?{param}={uuid.uuid4()}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_messages_cursor_from_other_channel_400(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed_timeline(db_session, 2)
    other_user, _, other_messages = await _seed_timeline(db_session, 1)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?after={other_messages[0].id}",
        headers=auth_header(user.id),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(("limit", "status"), [(200, 200), (201, 422), (0, 422)])
async def test_list_messages_limit_bounds(
    client: AsyncClient, db_session: AsyncSession, limit: int, status: int
) -> None:
    """Gap fill asks for up to 200 in one request (S4.3)."""
    user, channel, _ = await _seed(db_session)

    r = await client.get(
        f"/api/channels/{channel.id}/messages?limit={limit}",
        headers=auth_header(user.id),
    )
    assert r.status_code == status


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

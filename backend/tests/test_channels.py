"""Tests for /api/channels/* endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import MemberRole
from tests.conftest import auth_header
from tests.factories import ChannelFactory, ChannelMembershipFactory, UserFactory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_channel_with_member(
    db_session: AsyncSession,
    *,
    role: MemberRole = MemberRole.member,
) -> tuple:
    """Return (user, channel, membership)."""
    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()  # user must exist before channel (FK)

    channel = ChannelFactory.build(created_by=user.id)
    db_session.add(channel)
    await db_session.flush()  # channel must exist before membership (FK)

    membership = ChannelMembershipFactory.build(
        user_id=user.id,
        channel_id=channel.id,
        role=role,
    )
    db_session.add(membership)
    await db_session.commit()
    return user, channel, membership


# ---------------------------------------------------------------------------
# GET /api/channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_channels_returns_members_channels(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed_channel_with_member(db_session)
    other_channel = ChannelFactory.build(created_by=user.id)
    db_session.add(other_channel)
    await db_session.commit()

    response = await client.get("/api/channels", headers=auth_header(user.id))
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert str(channel.id) in ids
    assert str(other_channel.id) not in ids


@pytest.mark.asyncio
async def test_list_channels_no_token(client: AsyncClient) -> None:
    response = await client.get("/api/channels")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_channels_excludes_soft_deleted(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    from datetime import UTC, datetime

    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()

    channel = ChannelFactory.build(
        created_by=user.id,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(channel)
    await db_session.flush()

    membership = ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    db_session.add(membership)
    await db_session.commit()

    response = await client.get("/api/channels", headers=auth_header(user.id))
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# POST /api/channels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_channel(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/channels",
        json={"name": "general", "description": "Main channel"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "general"
    assert data["created_by"] == str(user.id)


@pytest.mark.asyncio
async def test_create_channel_no_token(client: AsyncClient) -> None:
    response = await client.post("/api/channels", json={"name": "x"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/channels/{channel_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_channel_detail(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed_channel_with_member(db_session)

    response = await client.get(
        f"/api/channels/{channel.id}", headers=auth_header(user.id)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(channel.id)
    assert len(data["members"]) == 1
    assert data["members"][0]["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_get_channel_403_not_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    outsider = UserFactory.build()
    db_session.add(outsider)
    await db_session.flush()

    channel = ChannelFactory.build(created_by=outsider.id)
    db_session.add(channel)
    await db_session.commit()

    response = await client.get(
        f"/api/channels/{channel.id}", headers=auth_header(outsider.id)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_channel_404(client: AsyncClient, db_session: AsyncSession) -> None:
    from datetime import UTC, datetime

    user = UserFactory.build()
    db_session.add(user)
    await db_session.flush()

    # Use a soft-deleted channel so the membership check passes but 404 is returned
    channel = ChannelFactory.build(
        created_by=user.id,
        deleted_at=datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(channel)
    await db_session.flush()

    membership = ChannelMembershipFactory.build(user_id=user.id, channel_id=channel.id)
    db_session.add(membership)
    await db_session.commit()

    response = await client.get(
        f"/api/channels/{channel.id}", headers=auth_header(user.id)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_channel_no_token(client: AsyncClient) -> None:
    response = await client.get(f"/api/channels/{uuid.uuid4()}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/channels/{channel_id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_channel_admin(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed_channel_with_member(
        db_session, role=MemberRole.admin
    )

    response = await client.delete(
        f"/api/channels/{channel.id}", headers=auth_header(user.id)
    )
    assert response.status_code == 204

    # Confirm soft-deleted — should no longer appear in list
    list_response = await client.get("/api/channels", headers=auth_header(user.id))
    assert all(c["id"] != str(channel.id) for c in list_response.json())


@pytest.mark.asyncio
async def test_delete_channel_non_admin_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, channel, _ = await _seed_channel_with_member(
        db_session, role=MemberRole.member
    )

    response = await client.delete(
        f"/api/channels/{channel.id}", headers=auth_header(user.id)
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_channel_no_token(client: AsyncClient) -> None:
    response = await client.delete(f"/api/channels/{uuid.uuid4()}")
    assert response.status_code == 401

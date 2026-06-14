"""Tests for /api/dm endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from tests.factories import ChannelFactory, ChannelMembershipFactory, UserFactory


async def _seed_dm_channel(
    db_session: AsyncSession,
    user_a,
    user_b,
) -> tuple:
    """Return (channel, membership_a, membership_b) for an existing DM."""
    channel = ChannelFactory.build(
        is_dm=True,
        name=f"dm-{min(user_a.id, user_b.id)}-{max(user_a.id, user_b.id)}",
        created_by=user_a.id,
    )
    db_session.add(channel)
    await db_session.flush()

    membership_a = ChannelMembershipFactory.build(
        user_id=user_a.id,
        channel_id=channel.id,
    )
    membership_b = ChannelMembershipFactory.build(
        user_id=user_b.id,
        channel_id=channel.id,
    )
    db_session.add(membership_a)
    db_session.add(membership_b)
    await db_session.commit()
    return channel, membership_a, membership_b


# ---------------------------------------------------------------------------
# POST /api/dm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_dm_channel(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build()
    target = UserFactory.build()
    db_session.add(user)
    db_session.add(target)
    await db_session.commit()

    response = await client.post(
        "/api/dm",
        json={"user_id": str(target.id)},
        headers=auth_header(user.id),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["is_dm"] is True
    assert data["other_user"]["id"] == str(target.id)
    assert data["other_user"]["name"] == target.name


@pytest.mark.asyncio
async def test_create_dm_returns_existing_channel(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build()
    target = UserFactory.build()
    db_session.add(user)
    db_session.add(target)
    await db_session.flush()

    channel, _, _ = await _seed_dm_channel(db_session, user, target)

    response = await client.post(
        "/api/dm",
        json={"user_id": str(target.id)},
        headers=auth_header(user.id),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(channel.id)
    assert data["other_user"]["id"] == str(target.id)


@pytest.mark.asyncio
async def test_create_dm_self_forbidden(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/dm",
        json={"user_id": str(user.id)},
        headers=auth_header(user.id),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_dm_target_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/dm",
        json={"user_id": str(uuid.uuid4())},
        headers=auth_header(user.id),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dm_no_token(client: AsyncClient) -> None:
    response = await client.post("/api/dm", json={"user_id": str(uuid.uuid4())})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/dm
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_dm_channels(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build()
    target_a = UserFactory.build()
    target_b = UserFactory.build()
    db_session.add(user)
    db_session.add(target_a)
    db_session.add(target_b)
    await db_session.flush()

    await _seed_dm_channel(db_session, user, target_a)
    await _seed_dm_channel(db_session, user, target_b)

    # Public channel for same user — should not appear in DM list
    public = ChannelFactory.build(created_by=user.id, is_dm=False)
    db_session.add(public)
    await db_session.flush()
    db_session.add(
        ChannelMembershipFactory.build(user_id=user.id, channel_id=public.id)
    )
    await db_session.commit()

    response = await client.get("/api/dm", headers=auth_header(user.id))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    other_ids = {d["other_user"]["id"] for d in data}
    assert str(target_a.id) in other_ids
    assert str(target_b.id) in other_ids
    assert all(d["is_dm"] is True for d in data)


@pytest.mark.asyncio
async def test_list_dm_channels_no_token(client: AsyncClient) -> None:
    response = await client.get("/api/dm")
    assert response.status_code == 401

"""Tests for /api/users/* endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header
from tests.factories import UserFactory


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.get("/api/users/me", headers=auth_header(user.id))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(user.id)
    assert data["email"] == user.email
    assert data["name"] == user.name


@pytest.mark.asyncio
async def test_get_me_no_token(client: AsyncClient) -> None:
    response = await client.get("/api/users/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/users/me", headers={"Authorization": "Bearer notavalidtoken"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_me_name(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build(name="Old Name")
    db_session.add(user)
    await db_session.commit()

    response = await client.patch(
        "/api/users/me",
        json={"name": "New Name"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 200
    assert response.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_patch_me_avatar(client: AsyncClient, db_session: AsyncSession) -> None:
    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.patch(
        "/api/users/me",
        json={"avatar_url": "https://example.com/avatar.png"},
        headers=auth_header(user.id),
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"] == "https://example.com/avatar.png"


@pytest.mark.asyncio
async def test_patch_me_no_token(client: AsyncClient) -> None:
    response = await client.patch("/api/users/me", json={"name": "x"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_user_public_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    requester = UserFactory.build()
    target = UserFactory.build()
    db_session.add(requester)
    db_session.add(target)
    await db_session.commit()

    response = await client.get(
        f"/api/users/{target.id}", headers=auth_header(requester.id)
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(target.id)


@pytest.mark.asyncio
async def test_get_user_not_found(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    import uuid

    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

    response = await client.get(
        f"/api/users/{uuid.uuid4()}", headers=auth_header(user.id)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_user_no_token(client: AsyncClient) -> None:
    import uuid

    response = await client.get(f"/api/users/{uuid.uuid4()}")
    assert response.status_code == 401

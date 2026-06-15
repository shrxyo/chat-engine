"""Tests for /api/auth/sync endpoint."""

import uuid

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from tests.factories import UserFactory

settings = get_settings()


@pytest.mark.asyncio
async def test_sync_creates_new_user(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/sync",
        json={
            "email": "new@example.com",
            "name": "New User",
            "avatar_url": "https://example.com/avatar.png",
            "provider": "github",
            "provider_id": "12345",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "user_id" in data
    assert "access_token" in data

    user_id = uuid.UUID(data["user_id"])
    payload = jwt.decode(
        data["access_token"], settings.SECRET_KEY, algorithms=["HS256"]
    )
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "new@example.com"
    assert payload["name"] == "New User"

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_response.status_code == 200
    me = me_response.json()
    assert me["id"] == str(user_id)
    assert me["email"] == "new@example.com"
    assert me["name"] == "New User"


@pytest.mark.asyncio
async def test_sync_upserts_existing_provider_user(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user = UserFactory.build(
        email="old@example.com",
        name="Old Name",
        provider="github",
        provider_id="999",
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/auth/sync",
        json={
            "email": "updated@example.com",
            "name": "Updated Name",
            "avatar_url": "https://example.com/new.png",
            "provider": "github",
            "provider_id": "999",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user.id)

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_response.status_code == 200
    me = me_response.json()
    assert me["email"] == "updated@example.com"
    assert me["name"] == "Updated Name"
    assert me["avatar_url"] == "https://example.com/new.png"


@pytest.mark.asyncio
async def test_sync_validation_error(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/sync",
        json={"email": "bad-email", "name": "x"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_sync_token_works_with_protected_route(client: AsyncClient) -> None:
    response = await client.post(
        "/api/auth/sync",
        json={
            "email": "token@example.com",
            "name": "Token User",
            "avatar_url": None,
            "provider": "google",
            "provider_id": "oauth-1",
        },
    )
    assert response.status_code == 200
    token = response.json()["access_token"]

    me_response = await client.get(
        "/api/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "token@example.com"

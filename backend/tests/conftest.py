"""
Shared pytest fixtures.

Test isolation strategy:
- All tests run against a dedicated `chatdb_test` database.
- Tables are created once per session via SQLModel.metadata.create_all.
- A `clean_tables` autouse fixture truncates every table BEFORE each test,
  guaranteeing a clean slate regardless of what the previous test did.
- `db_session` is used only for test-side inserts; the FastAPI app gets its
  own independent sessions via the `client` fixture's dependency override.
  This avoids event-loop / post-commit lifecycle conflicts between the test
  session and route-handler sessions.
- Always `await db_session.commit()` (or flush) before calling the HTTP client
  so that route-handler sessions can see the test data.
"""

import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import asyncpg
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

import app.models  # noqa: F401 — registers all SQLModel metadata
from app.config import get_settings
from app.database import get_session
from app.main import create_app

settings = get_settings()

# ---------------------------------------------------------------------------
# Test database
# ---------------------------------------------------------------------------
_TEST_DB_NAME = "chatdb_test"
TEST_DATABASE_URL: str = re.sub(r"/[^/?]+$", f"/{_TEST_DB_NAME}", settings.DATABASE_URL)

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool, echo=False)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


# ---------------------------------------------------------------------------
# Session-scoped: create the test DB (if absent) and all tables once per run
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    admin_url = re.sub(r"/[^/?]+$", "/postgres", settings.DATABASE_URL)
    admin_url_asyncpg = admin_url.replace("postgresql+asyncpg://", "postgresql://")

    conn: asyncpg.Connection[Any] = await asyncpg.connect(admin_url_asyncpg)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            _TEST_DB_NAME,
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    finally:
        await conn.close()

    async with test_engine.begin() as db_conn:
        await db_conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db_conn.run_sync(SQLModel.metadata.create_all)

    yield

    async with test_engine.begin() as db_conn:
        await db_conn.run_sync(SQLModel.metadata.drop_all)

    await test_engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped: truncate all rows BEFORE each test (pre-yield)
# ---------------------------------------------------------------------------

_TRUNCATE_SQL = text(
    "TRUNCATE TABLE"
    " message_reactions, message_attachments, messages,"
    " channel_memberships, channels, users"
    " CASCADE"
)


@pytest_asyncio.fixture(autouse=True)
async def clean_tables() -> AsyncGenerator[None, None]:
    async with TestSessionLocal() as session:
        await session.execute(_TRUNCATE_SQL)
        await session.commit()
    yield


# ---------------------------------------------------------------------------
# Per-test DB session (for test-side inserts only)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# HTTP client — routes get their own independent sessions
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app = create_app()

    async def _override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------


def make_token(user_id: uuid.UUID) -> str:
    return jwt.encode({"sub": str(user_id)}, settings.SECRET_KEY, algorithm="HS256")


def auth_header(user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(user_id)}"}

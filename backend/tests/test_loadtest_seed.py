"""S6.4: load-test seed (users in fixed-size rooms + minted JWTs)."""

import json
import uuid
from pathlib import Path

import pytest
from jose import jwt
from scripts.loadtest_seed import seed_load_users, write_tokens
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.channel import Channel
from app.models.membership import ChannelMembership
from app.models.user import User
from tests.factories import UserFactory

settings = get_settings()

# Same loop as the session-scoped engine fixtures (see test_db_pool_indexes.py).
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _count(session: AsyncSession, model: type) -> int:
    result = await session.execute(select(func.count()).select_from(model))
    return int(result.scalar_one())


async def test_creates_users_in_rooms(db_session: AsyncSession) -> None:
    entries = await seed_load_users(db_session, settings, users=7, room_size=3)

    assert len(entries) == 7
    assert await _count(db_session, User) == 7
    # 7 users in rooms of 3 → rooms of 3, 3, 1
    assert await _count(db_session, Channel) == 3
    assert await _count(db_session, ChannelMembership) == 7

    rooms: dict[str, list[str]] = {}
    for e in entries:
        rooms.setdefault(e["channel_id"], []).append(e["user_id"])
    assert sorted(len(m) for m in rooms.values()) == [1, 3, 3]

    for e in entries:
        membership = await db_session.get(
            ChannelMembership, (uuid.UUID(e["user_id"]), uuid.UUID(e["channel_id"]))
        )
        assert membership is not None


async def test_tokens_authenticate_as_the_user(db_session: AsyncSession) -> None:
    entries = await seed_load_users(db_session, settings, users=2, room_size=2)

    for e in entries:
        claims = jwt.decode(e["token"], settings.SECRET_KEY, algorithms=["HS256"])
        assert claims["sub"] == e["user_id"]
        assert "exp" in claims


async def test_rerun_reuses_rows(db_session: AsyncSession) -> None:
    first = await seed_load_users(db_session, settings, users=5, room_size=2)
    second = await seed_load_users(db_session, settings, users=5, room_size=2)

    assert [(e["user_id"], e["channel_id"]) for e in first] == [
        (e["user_id"], e["channel_id"]) for e in second
    ]
    assert await _count(db_session, User) == 5
    assert await _count(db_session, Channel) == 3
    assert await _count(db_session, ChannelMembership) == 5


async def test_rerun_with_more_users_extends(db_session: AsyncSession) -> None:
    await seed_load_users(db_session, settings, users=3, room_size=2)
    entries = await seed_load_users(db_session, settings, users=6, room_size=2)

    assert len(entries) == 6
    assert await _count(db_session, User) == 6
    assert await _count(db_session, Channel) == 3
    assert await _count(db_session, ChannelMembership) == 6


async def test_leaves_other_users_alone(db_session: AsyncSession) -> None:
    other = UserFactory.build()
    db_session.add(other)
    await db_session.commit()

    await seed_load_users(db_session, settings, users=2, room_size=2)

    assert await db_session.get(User, other.id) is not None
    members = await db_session.execute(
        select(ChannelMembership).where(ChannelMembership.user_id == other.id)
    )
    assert members.first() is None


@pytest.mark.parametrize(("users", "room_size"), [(0, 2), (2, 0)])
async def test_rejects_bad_sizes(
    db_session: AsyncSession, users: int, room_size: int
) -> None:
    with pytest.raises(ValueError):
        await seed_load_users(db_session, settings, users=users, room_size=room_size)


def test_write_tokens(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "tokens.json"
    entries = [{"user_id": "u", "channel_id": "c", "token": "t"}]

    write_tokens(out, entries)

    assert json.loads(out.read_text()) == entries
    # Tokens are credentials: owner-only.
    assert out.stat().st_mode & 0o077 == 0

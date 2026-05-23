"""Development seed script.

Creates 5 users, 3 channels, memberships, and 50 messages spread across the
last 30 days. Safe to run repeatedly — aborts early if users already exist.

Usage:
    cd backend
    uv run python scripts/seed.py
"""

import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Ensure src/ is importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from faker import Faker
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.channel import Channel
from app.models.membership import ChannelMembership, MemberRole
from app.models.message import Message
from app.models.user import User

fake = Faker()
settings = get_settings()


async def already_seeded(session: AsyncSession) -> bool:
    result = await session.execute(select(User).limit(1))
    return result.first() is not None


async def seed(session: AsyncSession) -> None:
    if await already_seeded(session):
        print("Database already seeded — skipping.")
        return

    # ── Users ────────────────────────────────────────────────────────────
    users: list[User] = []
    for _ in range(5):
        user = User(
            email=fake.unique.email(),
            name=fake.name(),
            avatar_url=f"https://api.dicebear.com/7.x/avataaars/svg?seed={uuid.uuid4().hex}",
            provider="github",
            provider_id=str(fake.random_int(min=100000, max=9999999)),
        )
        session.add(user)
        users.append(user)

    await session.flush()  # assign IDs before FK references

    # ── Channels ─────────────────────────────────────────────────────────
    channel_specs = [
        ("general", "Company-wide announcements and discussion"),
        ("engineering", "Engineering team discussion"),
        ("random", "Off-topic chat"),
    ]
    channels: list[Channel] = []
    for name, description in channel_specs:
        channel = Channel(
            name=name,
            description=description,
            is_dm=False,
            created_by=users[0].id,
        )
        session.add(channel)
        channels.append(channel)

    await session.flush()

    # ── Memberships ───────────────────────────────────────────────────────
    for channel in channels:
        for i, user in enumerate(users):
            membership = ChannelMembership(
                user_id=user.id,
                channel_id=channel.id,
                role=MemberRole.admin if i == 0 else MemberRole.member,
            )
            session.add(membership)

    await session.flush()

    # ── Messages ──────────────────────────────────────────────────────────
    now = datetime.utcnow()
    for _ in range(50):
        age_days = random.uniform(0, 30)
        created_at = now - timedelta(days=age_days)
        message = Message(
            channel_id=random.choice(channels).id,
            user_id=random.choice(users).id,
            content=fake.sentence(nb_words=random.randint(5, 30)),
            created_at=created_at,
        )
        session.add(message)

    await session.commit()
    print(
        f"Seeded {len(users)} users, {len(channels)} channels, "
        "and 50 messages successfully."
    )


async def main() -> None:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

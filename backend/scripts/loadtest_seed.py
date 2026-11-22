"""Load-test seed (S6.4).

Creates N load-test users split into rooms (channels) of a fixed size, one
membership each, and mints a JWT per user with the configured SECRET_KEY.
Writes `[{user_id, channel_id, token}, ...]` to a JSON file that the k6 script
reads. Rerunning reuses existing rows, so tokens can be refreshed cheaply.

Load-test rows are marked by `provider="loadtest"` and channel names
`loadtest-NNNN`; nothing else is touched.

Usage (from backend/, against the compose Postgres on :5433):
    uv run python scripts/loadtest_seed.py --users 1000 --room-size 10 \
        --out ../infra/load-tests/.data/tokens.json
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure src/ is importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import col, select

from app.config import Settings, get_settings
from app.models.channel import Channel
from app.models.membership import ChannelMembership
from app.models.user import User
from app.services.auth import create_access_token

PROVIDER = "loadtest"
EMAIL_DOMAIN = "loadtest.invalid"  # RFC 2606: never routable

Entry = dict[str, str]


def _email(i: int) -> str:
    return f"loadtest-{i:05d}@{EMAIL_DOMAIN}"


def _room_name(j: int) -> str:
    return f"loadtest-{j:04d}"


async def seed_load_users(
    session: AsyncSession, settings: Settings, *, users: int, room_size: int
) -> list[Entry]:
    """Create or reuse `users` load-test users in rooms of `room_size`."""
    if users < 1 or room_size < 1:
        raise ValueError("users and room_size must be >= 1")

    # --- Users ---
    emails = [_email(i) for i in range(users)]
    users_result = await session.execute(
        select(User).where(col(User.provider) == PROVIDER)
    )
    by_email = {u.email: u for u in users_result.scalars()}
    for i, email in enumerate(emails):
        if email not in by_email:
            user = User(
                email=email,
                name=f"Load Test {i:05d}",
                provider=PROVIDER,
                provider_id=str(i),
            )
            session.add(user)
            by_email[email] = user
    await session.flush()
    ordered = [by_email[e] for e in emails]

    # --- Rooms ---
    room_count = -(-users // room_size)
    names = [_room_name(j) for j in range(room_count)]
    channels_result = await session.execute(
        select(Channel).where(
            col(Channel.name).in_(names), col(Channel.is_dm).is_(False)
        )
    )
    by_name = {c.name: c for c in channels_result.scalars()}
    for j, name in enumerate(names):
        if name not in by_name:
            channel = Channel(
                name=name,
                description="k6 load-test room",
                created_by=ordered[j * room_size].id,
            )
            session.add(channel)
            by_name[name] = channel
    await session.flush()

    # --- Memberships ---
    room_ids = {by_name[n].id for n in names}
    members_result = await session.execute(
        select(col(ChannelMembership.user_id), col(ChannelMembership.channel_id)).where(
            col(ChannelMembership.channel_id).in_(room_ids)
        )
    )
    existing = {(user_id, channel_id) for user_id, channel_id in members_result.all()}

    entries: list[Entry] = []
    for i, user in enumerate(ordered):
        channel = by_name[names[i // room_size]]
        if (user.id, channel.id) not in existing:
            session.add(ChannelMembership(user_id=user.id, channel_id=channel.id))
        entries.append(
            {
                "user_id": str(user.id),
                "channel_id": str(channel.id),
                "token": create_access_token(user, settings),
            }
        )

    await session.commit()
    return entries


def write_tokens(path: Path, entries: list[Entry]) -> None:
    """Write entries as JSON, readable by the owner only (they are credentials)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f)
    os.chmod(path, 0o600)


async def _main(users: int, room_size: int, out: Path) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        entries = await seed_load_users(
            session, settings, users=users, room_size=room_size
        )
    await engine.dispose()
    write_tokens(out, entries)
    rooms = len({e["channel_id"] for e in entries})
    print(f"{len(entries)} users in {rooms} rooms -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed k6 load-test users (S6.4).")
    parser.add_argument("--users", type=int, default=1000)
    parser.add_argument("--room-size", type=int, default=10)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[2]
        / "infra/load-tests/.data/tokens.json",
    )
    args = parser.parse_args()
    asyncio.run(_main(args.users, args.room_size, args.out))

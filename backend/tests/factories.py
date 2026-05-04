"""
factory_boy build-only factories for SQLModel table classes.

Usage (inside an async test):

    user = UserFactory.build()
    db_session.add(user)
    await db_session.commit()

Use `build()` (not `create()`) because the session is async; the test is
responsible for adding the instance and committing.
"""

import uuid
from datetime import UTC, datetime

import factory

from app.models.channel import Channel
from app.models.membership import ChannelMembership, MemberRole
from app.models.message import Message
from app.models.user import User


class UserFactory(factory.Factory):
    class Meta:
        model = User

    id = factory.LazyFunction(uuid.uuid4)
    email = factory.Sequence(lambda n: f"user{n}@example.com")
    name = factory.Sequence(lambda n: f"Test User {n}")
    avatar_url = None
    provider = "email"
    provider_id = factory.Sequence(lambda n: str(n))
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))


class ChannelFactory(factory.Factory):
    class Meta:
        model = Channel

    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"channel-{n}")
    description = None
    is_dm = False
    created_by = factory.LazyFunction(uuid.uuid4)
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))
    deleted_at = None


class ChannelMembershipFactory(factory.Factory):
    class Meta:
        model = ChannelMembership

    user_id = factory.LazyFunction(uuid.uuid4)
    channel_id = factory.LazyFunction(uuid.uuid4)
    role = MemberRole.member
    joined_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))


class MessageFactory(factory.Factory):
    class Meta:
        model = Message

    id = factory.LazyFunction(uuid.uuid4)
    channel_id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.LazyFunction(uuid.uuid4)
    content = factory.Sequence(lambda n: f"Message content {n}")
    embedding = None
    reply_to_id = None
    edited_at = None
    deleted_at = None
    created_at = factory.LazyFunction(lambda: datetime.now(UTC).replace(tzinfo=None))

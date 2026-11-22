import enum
import uuid
from datetime import datetime

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class MemberRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class ChannelMembership(SQLModel, table=True):
    __tablename__ = "channel_memberships"
    __table_args__ = (
        # The PK (user_id, channel_id) covers lookups by user. This covers
        # lookups by channel: member lists, DM pair search.
        Index("ix_channel_memberships_channel_id", "channel_id"),
    )

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", primary_key=True)
    role: MemberRole = Field(default=MemberRole.member, max_length=16)
    joined_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

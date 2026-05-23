import enum
import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class MemberRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class ChannelMembership(SQLModel, table=True):
    __tablename__ = "channel_memberships"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", primary_key=True)
    role: MemberRole = Field(default=MemberRole.member, max_length=16)
    joined_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

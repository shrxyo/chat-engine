# Import all models here so Alembic autogenerate picks up every table.
from app.models.attachment import MessageAttachment
from app.models.channel import Channel
from app.models.membership import ChannelMembership, MemberRole
from app.models.message import Message
from app.models.reaction import MessageReaction
from app.models.user import User

__all__ = [
    "User",
    "Channel",
    "ChannelMembership",
    "MemberRole",
    "Message",
    "MessageReaction",
    "MessageAttachment",
]

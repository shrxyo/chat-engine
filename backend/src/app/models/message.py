import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, text
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "messages"
    __table_args__ = (
        # Channel history: WHERE channel_id = ? AND deleted_at IS NULL
        # ORDER BY created_at, id, plus (created_at, id) row-comparison
        # cursors (S4.3). One index scan, no sort. Partial so soft-deleted
        # rows don't take up space in it.
        Index(
            "ix_messages_channel_id_created_at_id_live",
            "channel_id",
            "created_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    content: str = Field(nullable=False)
    embedding: list[float] | None = Field(
        default=None, sa_column=Column(Vector(1536), nullable=True)
    )
    reply_to_id: uuid.UUID | None = Field(
        default=None, foreign_key="messages.id", nullable=True
    )
    edited_at: datetime | None = Field(default=None, nullable=True)
    deleted_at: datetime | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=datetime.utcnow, nullable=False, index=True
    )

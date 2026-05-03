import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    channel_id: uuid.UUID = Field(foreign_key="channels.id", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)
    content: str = Field(nullable=False)
    embedding: Optional[list[float]] = Field(
        default=None, sa_column=Column(Vector(1536), nullable=True)
    )
    reply_to_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="messages.id", nullable=True
    )
    edited_at: Optional[datetime] = Field(default=None, nullable=True)
    deleted_at: Optional[datetime] = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)

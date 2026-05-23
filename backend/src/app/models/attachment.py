import uuid
from datetime import datetime

from sqlmodel import Field, SQLModel


class MessageAttachment(SQLModel, table=True):
    __tablename__ = "message_attachments"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    message_id: uuid.UUID = Field(foreign_key="messages.id", nullable=False, index=True)
    filename: str = Field(max_length=512, nullable=False)
    content_type: str = Field(max_length=128, nullable=False)
    url: str = Field(max_length=2048, nullable=False)
    size_bytes: int = Field(nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)

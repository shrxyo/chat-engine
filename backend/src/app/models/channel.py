import uuid
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class Channel(SQLModel, table=True):
    __tablename__ = "channels"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=128, index=True)
    description: Optional[str] = Field(default=None, max_length=1024)
    is_dm: bool = Field(default=False, nullable=False)
    created_by: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )

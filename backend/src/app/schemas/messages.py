import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    user_id: uuid.UUID
    content: str
    reply_to_id: uuid.UUID | None = None
    edited_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    has_more: bool


class MessageUpdateRequest(BaseModel):
    content: str = Field(min_length=1)

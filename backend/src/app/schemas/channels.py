import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.membership import MemberRole


class ChannelCreateRequest(BaseModel):
    name: str
    description: str | None = None
    is_dm: bool = False


class ChannelResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_dm: bool
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    channel_id: uuid.UUID
    role: MemberRole
    joined_at: datetime

    model_config = {"from_attributes": True}


class ChannelDetailResponse(ChannelResponse):
    members: list[MemberResponse]

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.users import UserResponse


class DMCreateRequest(BaseModel):
    user_id: uuid.UUID


class DMResponse(BaseModel):
    id: uuid.UUID
    is_dm: bool
    other_user: UserResponse
    created_at: datetime
    updated_at: datetime

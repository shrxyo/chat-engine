import uuid

from pydantic import BaseModel, Field


class AuthSyncRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    avatar_url: str | None = Field(default=None, max_length=2048)
    provider: str = Field(min_length=1, max_length=64)
    provider_id: str = Field(min_length=1, max_length=255)


class AuthSyncResponse(BaseModel):
    user_id: uuid.UUID
    access_token: str

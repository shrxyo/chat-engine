import uuid
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.messages import MessageResponse


class WSMessageType(StrEnum):
    # Inbound: client → server
    message_new = "message.new"
    message_edit = "message.edit"
    message_delete = "message.delete"
    message_reaction = "message.reaction"
    typing_start = "typing.start"
    typing_stop = "typing.stop"
    # Outbound: server → client
    presence_join = "presence.join"
    presence_leave = "presence.leave"
    error = "error"


# ---------------------------------------------------------------------------
# Inbound payload models (validated on receipt)
# ---------------------------------------------------------------------------


class MessageNewPayload(BaseModel):
    content: str = Field(min_length=1)
    reply_to_id: uuid.UUID | None = None


class MessageEditPayload(BaseModel):
    message_id: uuid.UUID
    content: str = Field(min_length=1)


class MessageDeletePayload(BaseModel):
    message_id: uuid.UUID


class MessageReactionPayload(BaseModel):
    message_id: uuid.UUID
    emoji: str = Field(min_length=1, max_length=32)


# ---------------------------------------------------------------------------
# Outbound payload models
# ---------------------------------------------------------------------------


class MessageNewBroadcastPayload(MessageResponse):
    # Epoch ms when the server received the message (S7.3). Used for
    # receive → fanout latency on every instance, and by load tests.
    server_ts: int

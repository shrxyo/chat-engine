import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies import ChannelMemberDep, CurrentUser, SessionDep
from app.models.message import Message
from app.schemas.messages import (
    MessageListResponse,
    MessageResponse,
    MessageUpdateRequest,
)
from app.services.messages import UnknownCursorError, list_channel_messages

router = APIRouter(tags=["messages"])


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    channel_id: uuid.UUID,
    _: ChannelMemberDep,
    session: SessionDep,
    before: Annotated[
        uuid.UUID | None,
        Query(description="Cursor: messages older than this message id"),
    ] = None,
    after: Annotated[
        uuid.UUID | None,
        Query(
            description=(
                "Cursor: the `limit` messages just newer than this message id "
                "(reconnect gap fill). has_more=true means more remain."
            )
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MessageListResponse:
    """Messages newest-first, ordered by (created_at, id)."""
    if before is not None and after is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use either before or after, not both",
        )
    try:
        messages, has_more = await list_channel_messages(
            session, channel_id, limit=limit, before=before, after=after
        )
    except UnknownCursorError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cursor is not a message in this channel",
        ) from None

    return MessageListResponse(
        messages=[MessageResponse.model_validate(m) for m in messages],
        has_more=has_more,
    )


@router.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: uuid.UUID,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    message = await session.get(Message, message_id)
    if message is None or message.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    if message.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own messages",
        )

    message.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(message)
    await session.commit()


@router.patch("/messages/{message_id}", response_model=MessageResponse)
async def update_message(
    message_id: uuid.UUID,
    body: MessageUpdateRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> MessageResponse:
    message = await session.get(Message, message_id)
    if message is None or message.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    if message.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own messages",
        )

    message.content = body.content
    message.edited_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return MessageResponse.model_validate(message)

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import ChannelMemberDep, CurrentUser, SessionDep
from app.models.channel import Channel
from app.models.membership import ChannelMembership, MemberRole
from app.schemas.channels import (
    ChannelCreateRequest,
    ChannelDetailResponse,
    ChannelResponse,
    MemberResponse,
)

router = APIRouter(prefix="/channels", tags=["channels"])


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[ChannelResponse]:
    result = await session.execute(
        select(Channel)
        .join(ChannelMembership, Channel.id == ChannelMembership.channel_id)
        .where(ChannelMembership.user_id == current_user.id)
        .where(Channel.deleted_at.is_(None))
        .order_by(Channel.name)
    )
    return [ChannelResponse.model_validate(c) for c in result.scalars().all()]


@router.post("", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: ChannelCreateRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> ChannelResponse:
    channel = Channel(
        name=body.name,
        description=body.description,
        is_dm=body.is_dm,
        created_by=current_user.id,
    )
    session.add(channel)
    await session.flush()

    membership = ChannelMembership(
        user_id=current_user.id,
        channel_id=channel.id,
        role=MemberRole.admin,
    )
    session.add(membership)
    await session.commit()
    await session.refresh(channel)
    return ChannelResponse.model_validate(channel)


@router.get("/{channel_id}", response_model=ChannelDetailResponse)
async def get_channel(
    channel_id: uuid.UUID,
    _: ChannelMemberDep,
    session: SessionDep,
) -> ChannelDetailResponse:
    channel = await session.get(Channel, channel_id)
    if channel is None or channel.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    result = await session.execute(
        select(ChannelMembership).where(ChannelMembership.channel_id == channel_id)
    )
    members = [MemberResponse.model_validate(m) for m in result.scalars().all()]

    return ChannelDetailResponse(
        **ChannelResponse.model_validate(channel).model_dump(),
        members=members,
    )


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: uuid.UUID,
    membership: ChannelMemberDep,
    session: SessionDep,
) -> None:
    if membership.role != MemberRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete a channel",
        )

    channel = await session.get(Channel, channel_id)
    if channel is None or channel.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    channel.deleted_at = datetime.now(UTC).replace(tzinfo=None)
    session.add(channel)
    await session.commit()

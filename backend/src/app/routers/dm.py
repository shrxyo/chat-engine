from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.dependencies import CurrentUser, SessionDep
from app.models.channel import Channel
from app.models.membership import ChannelMembership
from app.models.user import User
from app.schemas.dm import DMCreateRequest, DMResponse
from app.schemas.users import UserResponse
from app.services.dm import (
    create_dm_channel,
    find_existing_dm,
    get_other_dm_member,
)

router = APIRouter(prefix="/dm", tags=["dm"])


def _to_dm_response(channel: Channel, other_user: User) -> DMResponse:
    return DMResponse(
        id=channel.id,
        is_dm=True,
        other_user=UserResponse.model_validate(other_user),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


@router.post("", response_model=DMResponse)
async def create_or_get_dm(
    body: DMCreateRequest,
    current_user: CurrentUser,
    session: SessionDep,
    response: Response,
) -> DMResponse:
    if body.user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a DM with yourself",
        )

    target_user = await session.get(User, body.user_id)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    existing = await find_existing_dm(session, current_user.id, body.user_id)
    if existing is not None:
        other_user = await get_other_dm_member(session, existing.id, current_user.id)
        response.status_code = status.HTTP_200_OK
        return _to_dm_response(existing, other_user)

    channel = await create_dm_channel(session, current_user, target_user)
    response.status_code = status.HTTP_201_CREATED
    return _to_dm_response(channel, target_user)


@router.get("", response_model=list[DMResponse])
async def list_dm_channels(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[DMResponse]:
    result = await session.execute(
        select(Channel)
        .join(ChannelMembership, Channel.id == ChannelMembership.channel_id)
        .where(ChannelMembership.user_id == current_user.id)
        .where(Channel.is_dm.is_(True))
        .where(Channel.deleted_at.is_(None))
        .order_by(Channel.updated_at.desc())
    )
    channels = result.scalars().all()

    dm_responses: list[DMResponse] = []
    for channel in channels:
        other_user = await get_other_dm_member(session, channel.id, current_user.id)
        dm_responses.append(_to_dm_response(channel, other_user))

    return dm_responses

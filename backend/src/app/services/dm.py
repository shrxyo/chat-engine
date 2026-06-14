import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.channel import Channel
from app.models.membership import ChannelMembership, MemberRole
from app.models.user import User


async def find_existing_dm(
    session: AsyncSession,
    current_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> Channel | None:
    """Return the DM channel shared by both users, if one exists."""
    two_member_channels = (
        select(ChannelMembership.channel_id)
        .group_by(ChannelMembership.channel_id)
        .having(func.count() == 2)
        .scalar_subquery()
    )

    result = await session.execute(
        select(Channel)
        .join(ChannelMembership, Channel.id == ChannelMembership.channel_id)
        .where(Channel.is_dm.is_(True))
        .where(Channel.deleted_at.is_(None))
        .where(ChannelMembership.user_id == current_user_id)
        .where(
            Channel.id.in_(
                select(ChannelMembership.channel_id).where(
                    ChannelMembership.user_id == target_user_id
                )
            )
        )
        .where(Channel.id.in_(two_member_channels))
    )
    return result.scalars().first()


async def get_other_dm_member(
    session: AsyncSession,
    channel_id: uuid.UUID,
    current_user_id: uuid.UUID,
) -> User:
    result = await session.execute(
        select(User)
        .join(ChannelMembership, User.id == ChannelMembership.user_id)
        .where(ChannelMembership.channel_id == channel_id)
        .where(ChannelMembership.user_id != current_user_id)
    )
    other_user = result.scalars().first()
    if other_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Other DM participant not found",
        )
    return other_user


async def create_dm_channel(
    session: AsyncSession,
    current_user: User,
    target_user: User,
) -> Channel:
    channel = Channel(
        name=target_user.name,
        is_dm=True,
        created_by=current_user.id,
    )
    session.add(channel)
    await session.flush()

    for user_id in (current_user.id, target_user.id):
        session.add(
            ChannelMembership(
                user_id=user_id,
                channel_id=channel.id,
                role=MemberRole.member,
            )
        )

    await session.commit()
    await session.refresh(channel)
    return channel

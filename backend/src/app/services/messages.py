"""Channel message history with time-ordered cursors (S4.3).

Message ids are random uuid4, so they carry no order. Pages are ordered by
``(created_at, id)``; a ``before``/``after`` cursor is a message id that is
resolved to its ``(created_at, id)`` position. ``id`` only breaks ties.
"""

import uuid
from datetime import datetime

from sqlalchemy import ColumnElement, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from app.models.message import Message


class UnknownCursorError(ValueError):
    """The cursor id is not a message in this channel."""


_message_position = tuple_(col(Message.created_at), col(Message.id))


async def _cursor_position(
    session: AsyncSession, channel_id: uuid.UUID, cursor: uuid.UUID
) -> ColumnElement[tuple[datetime, uuid.UUID]]:
    # Soft-deleted cursors still count: the client may hold a message that
    # was deleted while it was disconnected.
    result = await session.execute(
        select(col(Message.created_at)).where(
            col(Message.id) == cursor, col(Message.channel_id) == channel_id
        )
    )
    created_at = result.scalar_one_or_none()
    if created_at is None:
        raise UnknownCursorError(str(cursor))
    return tuple_(literal(created_at), literal(cursor))


async def list_channel_messages(
    session: AsyncSession,
    channel_id: uuid.UUID,
    *,
    limit: int,
    before: uuid.UUID | None = None,
    after: uuid.UUID | None = None,
) -> tuple[list[Message], bool]:
    """Return ``(messages newest-first, has_more)``.

    - no cursor: the newest ``limit`` messages.
    - ``before``: the ``limit`` messages just older than the cursor.
    - ``after``: the ``limit`` messages just newer than the cursor, so a client
      can page forward with ``after=<newest returned>`` while ``has_more``.
    """
    if before is not None and after is not None:
        raise ValueError("before and after are mutually exclusive")

    query = (
        select(Message)
        .where(col(Message.channel_id) == channel_id)
        .where(col(Message.deleted_at).is_(None))
        .limit(limit + 1)
    )
    if after is not None:
        cursor = await _cursor_position(session, channel_id, after)
        query = query.where(_message_position > cursor).order_by(
            col(Message.created_at).asc(), col(Message.id).asc()
        )
    else:
        if before is not None:
            cursor = await _cursor_position(session, channel_id, before)
            query = query.where(_message_position < cursor)
        query = query.order_by(col(Message.created_at).desc(), col(Message.id).desc())

    rows = list((await session.execute(query)).scalars().all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    if after is not None:
        rows.reverse()
    return rows, has_more

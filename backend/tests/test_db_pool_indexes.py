"""S6.5 (partial): pooled engine + indexes for the hot read paths."""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.database import engine
from app.models.membership import ChannelMembership
from app.models.message import Message

# Same loop as the session-scoped fixtures. These tests never commit, so the
# db_session connection is still open at teardown and must close on its own loop.
pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Pool
# ---------------------------------------------------------------------------


def test_app_engine_uses_queue_pool() -> None:
    pool = engine.pool
    assert isinstance(pool, AsyncAdaptedQueuePool)
    assert pool.size() == 5
    assert pool._max_overflow == 15  # pyright: ignore[reportPrivateUsage]
    assert pool._pre_ping is True  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------


async def _index_names(session: AsyncSession, table: str) -> set[str]:
    result = await session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
    )
    return {row[0] for row in result}


async def _plan(session: AsyncSession, stmt: str, params: dict[str, object]) -> str:
    # Force index use where one fits, so the test does not depend on table
    # size or statistics. A seq scan here means no usable index exists.
    await session.execute(text("SET LOCAL enable_seqscan = off"))
    result = await session.execute(text(f"EXPLAIN {stmt}"), params)
    return "\n".join(row[0] for row in result)


async def test_message_list_index_exists(db_session: AsyncSession) -> None:
    names = await _index_names(db_session, "messages")
    assert "ix_messages_channel_id_created_at_id_live" in names
    # S4.3 replaced the (channel_id, id) index: random uuid4 ids have no order.
    assert "ix_messages_channel_id_id_live" not in names


async def test_membership_channel_index_exists(db_session: AsyncSession) -> None:
    names = await _index_names(db_session, "channel_memberships")
    assert "ix_channel_memberships_channel_id" in names


async def test_message_list_query_uses_index_without_sort(
    db_session: AsyncSession,
) -> None:
    """GET /channels/{id}/messages: filter + order served by one index scan."""
    query = (
        select(Message)
        .where(Message.channel_id == uuid.uuid4())
        .where(Message.deleted_at.is_(None))  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue, reportUnknownMemberType]
        .order_by(Message.created_at.desc(), Message.id.desc())  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        .limit(51)
    )
    compiled = query.compile(compile_kwargs={"literal_binds": True})
    plan = await _plan(db_session, str(compiled), {})
    assert "ix_messages_channel_id_created_at_id_live" in plan
    assert "Sort" not in plan


@pytest.mark.parametrize("direction", ["after", "before"])
async def test_message_cursor_query_uses_index_without_sort(
    db_session: AsyncSession, direction: str
) -> None:
    """S4.3: (created_at, id) row-comparison cursors are index conditions."""
    op, order = (">", "ASC") if direction == "after" else ("<", "DESC")
    stmt = (
        "SELECT id FROM messages WHERE channel_id = :ch AND deleted_at IS NULL "
        f"AND (created_at, id) {op} (:ts, :id) "
        f"ORDER BY created_at {order}, id {order} LIMIT 201"
    )
    plan = await _plan(
        db_session,
        stmt,
        {"ch": uuid.uuid4(), "ts": datetime(2026, 1, 1), "id": uuid.uuid4()},
    )
    assert "ix_messages_channel_id_created_at_id_live" in plan
    assert "Index Cond" in plan and "created_at" in plan.split("Index Cond", 1)[1]
    assert "Sort" not in plan


async def test_members_by_channel_query_uses_index(db_session: AsyncSession) -> None:
    """GET /channels/{id}: members looked up by channel_id alone."""
    query = select(ChannelMembership).where(
        ChannelMembership.channel_id == uuid.uuid4()
    )
    compiled = query.compile(compile_kwargs={"literal_binds": True})
    plan = await _plan(db_session, str(compiled), {})
    assert "ix_channel_memberships_channel_id" in plan

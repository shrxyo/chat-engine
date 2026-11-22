"""messages time-ordered history index

Revision ID: e4b8d2f6a913
Revises: c7e2a9f4b1d3
Create Date: 2026-11-21 23:00:00.000000

S4.3: channel history is now ordered and cursored by (created_at, id), since
message ids are random uuid4. Replaces ix_messages_channel_id_id_live, which
no query uses any more. Built CONCURRENTLY (no write lock on messages), so it
runs in an autocommit block. The new index is created before the old one is
dropped so history reads always have an index.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "e4b8d2f6a913"
down_revision: Union[str, Sequence[str], None] = "c7e2a9f4b1d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_messages_channel_id_created_at_id_live",
            "messages",
            ["channel_id", "created_at", "id"],
            postgresql_where="deleted_at IS NULL",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_messages_channel_id_id_live",
            table_name="messages",
            postgresql_concurrently=True,
            if_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_messages_channel_id_id_live",
            "messages",
            ["channel_id", "id"],
            postgresql_where="deleted_at IS NULL",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.drop_index(
            "ix_messages_channel_id_created_at_id_live",
            table_name="messages",
            postgresql_concurrently=True,
            if_exists=True,
        )

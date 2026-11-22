"""add hot path indexes

Revision ID: c7e2a9f4b1d3
Revises: a1b2c3d4e5f6
Create Date: 2026-11-21 19:30:00.000000

S6.5: indexes for channel history and member-by-channel lookups.
Built CONCURRENTLY so applying this on a live database does not block writes
to messages. CONCURRENTLY cannot run in a transaction, hence autocommit_block.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c7e2a9f4b1d3"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_messages_channel_id_id_live",
            "messages",
            ["channel_id", "id"],
            postgresql_where="deleted_at IS NULL",
            postgresql_concurrently=True,
            if_not_exists=True,
        )
        op.create_index(
            "ix_channel_memberships_channel_id",
            "channel_memberships",
            ["channel_id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_channel_memberships_channel_id",
            table_name="channel_memberships",
            postgresql_concurrently=True,
            if_exists=True,
        )
        op.drop_index(
            "ix_messages_channel_id_id_live",
            table_name="messages",
            postgresql_concurrently=True,
            if_exists=True,
        )

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add archived_at column to conversations for soft-archiving.

Revision ID: 008_add_conversation_archived_at
Revises: 007_create_contacts_tables
Create Date: 2026-01-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_conversation_archived_at"
down_revision: str | None = "007_create_contacts_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_conversations_archived_at",
        "conversations",
        ["archived_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_archived_at", table_name="conversations")
    op.drop_column("conversations", "archived_at")

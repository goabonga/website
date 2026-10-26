# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add summary column to conversations.

Revision ID: 003_add_conversation_summary
Revises: 002_drop_current_conversation_id
Create Date: 2026-01-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_add_conversation_summary"
down_revision: str | None = "002_drop_current_conversation_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("conversations", "summary")

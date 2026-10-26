# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""add user_cache table

Revision ID: 002
Revises: 001
Create Date: 2026-04-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_cache table."""
    op.create_table(
        "user_cache",
        sa.Column("sub", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("avatar_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sub"),
    )
    op.create_index("ix_user_cache_email", "user_cache", ["email"])


def downgrade() -> None:
    """Drop user_cache table."""
    op.drop_index("ix_user_cache_email", table_name="user_cache")
    op.drop_table("user_cache")

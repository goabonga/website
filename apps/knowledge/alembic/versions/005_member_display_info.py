# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add display_name and email columns to tenant_members.

Revision ID: 005_member_display_info
Revises: 004_workspace_deletion_requests
Create Date: 2026-01-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "005_member_display_info"
down_revision: str | None = "004_workspace_deletion_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add display_name column to tenant_members
    result = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'tenant_members' AND column_name = 'display_name'
            """
        )
    )
    if not result.fetchone():
        op.add_column(
            "tenant_members",
            sa.Column("display_name", sa.String(255), nullable=True),
        )

    # Add email column to tenant_members
    result = conn.execute(
        sa.text(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'tenant_members' AND column_name = 'email'
            """
        )
    )
    if not result.fetchone():
        op.add_column(
            "tenant_members",
            sa.Column("email", sa.String(255), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("tenant_members", "email")
    op.drop_column("tenant_members", "display_name")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add scheduled deletion support to workspace deletion requests.

Revision ID: 007_workspace_deletion_scheduled
Revises: 006_mcp_releases
Create Date: 2026-02-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "007_workspace_deletion_scheduled"
down_revision: str | None = "006_mcp_releases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add 'scheduled' value to deletionrequeststatus enum
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_enum WHERE enumlabel = 'scheduled' "
            "AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'deletionrequeststatus')"
        )
    )
    if not result.fetchone():
        op.execute("ALTER TYPE deletionrequeststatus ADD VALUE 'scheduled'")

    # Add new columns to workspace_deletion_requests
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workspace_deletion_requests' "
            "AND column_name = 'scheduled_deletion_at'"
        )
    )
    if not result.fetchone():
        op.execute(
            """
            ALTER TABLE workspace_deletion_requests
            ADD COLUMN scheduled_deletion_at TIMESTAMP WITH TIME ZONE
        """
        )

    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workspace_deletion_requests' "
            "AND column_name = 'subscription_cancelled'"
        )
    )
    if not result.fetchone():
        op.execute(
            """
            ALTER TABLE workspace_deletion_requests
            ADD COLUMN subscription_cancelled BOOLEAN NOT NULL DEFAULT false
        """
        )

    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workspace_deletion_requests' "
            "AND column_name = 'cancel_token'"
        )
    )
    if not result.fetchone():
        op.execute(
            """
            ALTER TABLE workspace_deletion_requests
            ADD COLUMN cancel_token VARCHAR(64) UNIQUE
        """
        )
        op.create_index(
            "ix_workspace_deletion_requests_cancel_token",
            "workspace_deletion_requests",
            ["cancel_token"],
        )

    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'workspace_deletion_requests' "
            "AND column_name = 'reminder_sent_at'"
        )
    )
    if not result.fetchone():
        op.execute(
            """
            ALTER TABLE workspace_deletion_requests
            ADD COLUMN reminder_sent_at TIMESTAMP WITH TIME ZONE
        """
        )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_deletion_requests_cancel_token",
        table_name="workspace_deletion_requests",
    )
    op.execute(
        """
        ALTER TABLE workspace_deletion_requests
        DROP COLUMN IF EXISTS scheduled_deletion_at,
        DROP COLUMN IF EXISTS subscription_cancelled,
        DROP COLUMN IF EXISTS cancel_token,
        DROP COLUMN IF EXISTS reminder_sent_at
    """
    )
    # Note: PostgreSQL doesn't support removing enum values easily
    # The 'scheduled' value will remain in the enum

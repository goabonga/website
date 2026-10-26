# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add workspace deletion requests table.

Revision ID: 004_workspace_deletion_requests
Revises: 003_github_ownership
Create Date: 2026-01-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004_workspace_deletion_requests"
down_revision: str | None = "003_github_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create deletion request status enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'deletionrequeststatus'"))
    if not result.fetchone():
        op.execute(
            "CREATE TYPE deletionrequeststatus AS ENUM ('pending', 'confirmed', 'expired', 'cancelled')"
        )

    # Create workspace_deletion_requests table
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'workspace_deletion_requests'"
        )
    )
    if not result.fetchone():
        op.execute(
            """
            CREATE TABLE workspace_deletion_requests (
                id UUID NOT NULL PRIMARY KEY,
                organization_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                requested_by UUID NOT NULL,
                email VARCHAR(255) NOT NULL,
                token VARCHAR(64) NOT NULL,
                status deletionrequeststatus NOT NULL DEFAULT 'pending',
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                confirmed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT uq_workspace_deletion_request_token UNIQUE (token)
            )
        """
        )
        op.create_index(
            "ix_workspace_deletion_requests_organization_id",
            "workspace_deletion_requests",
            ["organization_id"],
        )
        op.create_index(
            "ix_workspace_deletion_requests_token",
            "workspace_deletion_requests",
            ["token"],
        )


def downgrade() -> None:
    op.drop_table("workspace_deletion_requests")
    op.execute("DROP TYPE IF EXISTS deletionrequeststatus")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create personal_access_tokens table.

This migration creates the table for Personal Access Tokens (PATs),
allowing users to create fine-grained API tokens similar to GitHub's PATs.

Revision ID: 034
Revises: 033
Create Date: 2026-01-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "034"
down_revision: str | None = "033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_suffix", sa.String(length=4), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("target_client_id", sa.Uuid(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_ip", sa.String(length=45), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(), nullable=True),
        sa.Column("revocation_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_personal_access_tokens_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_personal_access_tokens_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_client_id"],
            ["oauth2_clients.id"],
            name=op.f("fk_personal_access_tokens_target_client_id_oauth2_clients"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["revoked_by"],
            ["users.id"],
            name=op.f("fk_personal_access_tokens_revoked_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_personal_access_tokens")),
    )

    # Indexes for fast lookups
    op.create_index(
        op.f("ix_personal_access_tokens_token_hash"),
        "personal_access_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_personal_access_tokens_user_id"),
        "personal_access_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_access_tokens_tenant_id"),
        "personal_access_tokens",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_personal_access_tokens_target_client_id"),
        "personal_access_tokens",
        ["target_client_id"],
        unique=False,
    )
    # Composite index for active tokens lookup by user
    op.create_index(
        "ix_personal_access_tokens_user_active",
        "personal_access_tokens",
        ["user_id", "revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personal_access_tokens_user_active",
        table_name="personal_access_tokens",
    )
    op.drop_index(
        op.f("ix_personal_access_tokens_target_client_id"),
        table_name="personal_access_tokens",
    )
    op.drop_index(
        op.f("ix_personal_access_tokens_tenant_id"),
        table_name="personal_access_tokens",
    )
    op.drop_index(
        op.f("ix_personal_access_tokens_user_id"),
        table_name="personal_access_tokens",
    )
    op.drop_index(
        op.f("ix_personal_access_tokens_token_hash"),
        table_name="personal_access_tokens",
    )
    op.drop_table("personal_access_tokens")

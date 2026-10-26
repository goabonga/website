# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add tenant_id to oauth2_clients and sessions for multi-tenant isolation.

Revision ID: 027
Revises: 025
Create Date: 2026-01-24

This migration adds optional tenant_id foreign key to:
- oauth2_clients: Clients can be scoped to a specific tenant
- sessions: Sessions are isolated by tenant for security

The tenant_id is nullable to maintain backward compatibility with
existing single-tenant deployments.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "027"
down_revision: str | None = "025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add tenant_id to oauth2_clients
    op.add_column(
        "oauth2_clients",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_oauth2_clients_tenant_id_tenants"),
        "oauth2_clients",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_oauth2_clients_tenant_id"),
        "oauth2_clients",
        ["tenant_id"],
        unique=False,
    )

    # Add tenant_id to sessions
    op.add_column(
        "sessions",
        sa.Column("tenant_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_sessions_tenant_id_tenants"),
        "sessions",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_sessions_tenant_id"),
        "sessions",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    # Remove tenant_id from sessions
    op.drop_index(op.f("ix_sessions_tenant_id"), table_name="sessions")
    op.drop_constraint(op.f("fk_sessions_tenant_id_tenants"), "sessions", type_="foreignkey")
    op.drop_column("sessions", "tenant_id")

    # Remove tenant_id from oauth2_clients
    op.drop_index(op.f("ix_oauth2_clients_tenant_id"), table_name="oauth2_clients")
    op.drop_constraint(
        op.f("fk_oauth2_clients_tenant_id_tenants"), "oauth2_clients", type_="foreignkey"
    )
    op.drop_column("oauth2_clients", "tenant_id")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add user registration source tracking fields.

Revision ID: 042
Revises: 034
Create Date: 2025-02-02

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "042"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add registration source tracking columns to users table."""
    op.add_column(
        "users",
        sa.Column(
            "registration_source",
            sa.String(50),
            nullable=True,
            comment="How user registered: 'direct' (auth UI), 'api' (client app), 'oauth' (social login)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "registration_client_id",
            sa.String(255),
            nullable=True,
            comment="OAuth client_id that created the user (for API registrations)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "registration_tenant_id",
            sa.UUID(),
            nullable=True,
            comment="Tenant context during registration (if any)",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "registration_ip",
            sa.String(45),
            nullable=True,
            comment="IP address at registration",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "registration_user_agent",
            sa.Text(),
            nullable=True,
            comment="User agent at registration",
        ),
    )

    # Add foreign key constraint for registration_tenant_id
    op.create_foreign_key(
        "fk_users_registration_tenant_id",
        "users",
        "tenants",
        ["registration_tenant_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index on registration_tenant_id for faster lookups
    op.create_index(
        "ix_users_registration_tenant_id",
        "users",
        ["registration_tenant_id"],
    )

    # Add index on registration_source for analytics queries
    op.create_index(
        "ix_users_registration_source",
        "users",
        ["registration_source"],
    )


def downgrade() -> None:
    """Remove registration source tracking columns from users table."""
    op.drop_index("ix_users_registration_source", table_name="users")
    op.drop_index("ix_users_registration_tenant_id", table_name="users")
    op.drop_constraint("fk_users_registration_tenant_id", "users", type_="foreignkey")
    op.drop_column("users", "registration_user_agent")
    op.drop_column("users", "registration_ip")
    op.drop_column("users", "registration_tenant_id")
    op.drop_column("users", "registration_client_id")
    op.drop_column("users", "registration_source")

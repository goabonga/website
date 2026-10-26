# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add tenant trust policies for cross-tenant login control.

Revision ID: 044
Revises: 043
Create Date: 2025-02-03

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add trust mode to tenants and create tenant_trusted_sources table."""
    # Create enum type for trust mode
    tenant_trust_mode_enum = sa.Enum(
        "none",
        "all",
        "members_only",
        "specific",
        name="tenanttrustmode",
    )
    tenant_trust_mode_enum.create(op.get_bind(), checkfirst=True)

    # Add trust_mode column to tenants table
    op.add_column(
        "tenants",
        sa.Column(
            "trust_mode",
            tenant_trust_mode_enum,
            nullable=False,
            server_default="none",
            comment="Controls which external users can login to this tenant",
        ),
    )

    # Create tenant_trusted_sources table
    op.create_table(
        "tenant_trusted_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "trusted_tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
            comment="The trusted tenant. NULL means main domain (users without a registration tenant)",
        ),
        sa.Column(
            "description",
            sa.String(255),
            nullable=True,
            comment="Description for admin UI",
        ),
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
        # Unique constraint: a tenant can only trust another tenant once
        sa.UniqueConstraint(
            "tenant_id", "trusted_tenant_id", name="uq_tenant_trusted_sources_tenant_trusted"
        ),
    )

    # Create index for efficient lookup
    op.create_index(
        "ix_tenant_trusted_sources_tenant",
        "tenant_trusted_sources",
        ["tenant_id"],
    )


def downgrade() -> None:
    """Remove trust mode from tenants and drop tenant_trusted_sources table."""
    op.drop_index("ix_tenant_trusted_sources_tenant", table_name="tenant_trusted_sources")
    op.drop_table("tenant_trusted_sources")
    op.drop_column("tenants", "trust_mode")

    # Drop enum type
    sa.Enum(name="tenanttrustmode").drop(op.get_bind(), checkfirst=True)

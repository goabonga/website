# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add custom domain status tracking fields to tenants.

Revision ID: 043
Revises: 042
Create Date: 2025-02-03

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add custom domain status tracking columns to tenants table."""
    # Create enum type for custom domain status
    custom_domain_status_enum = sa.Enum(
        "pending",
        "dns_verifying",
        "dns_verified",
        "ssl_provisioning",
        "active",
        "failed",
        name="customdomainstatus",
    )
    custom_domain_status_enum.create(op.get_bind(), checkfirst=True)

    # Add status column
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_status",
            custom_domain_status_enum,
            nullable=True,
            comment="Status of custom domain provisioning",
        ),
    )

    # Add verification timestamp
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When DNS was verified",
        ),
    )

    # Add SSL provisioned timestamp
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_ssl_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When SSL certificate was provisioned",
        ),
    )

    # Add error message column
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_error",
            sa.Text(),
            nullable=True,
            comment="Error message if provisioning failed",
        ),
    )

    # Add last check timestamp
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last time DNS was checked",
        ),
    )

    # Add index on status for periodic task queries
    op.create_index(
        "ix_tenants_custom_domain_status",
        "tenants",
        ["custom_domain_status"],
        postgresql_where=sa.text("custom_domain_status IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove custom domain status tracking columns from tenants table."""
    op.drop_index("ix_tenants_custom_domain_status", table_name="tenants")
    op.drop_column("tenants", "custom_domain_checked_at")
    op.drop_column("tenants", "custom_domain_error")
    op.drop_column("tenants", "custom_domain_ssl_at")
    op.drop_column("tenants", "custom_domain_verified_at")
    op.drop_column("tenants", "custom_domain_status")

    # Drop enum type
    sa.Enum(name="customdomainstatus").drop(op.get_bind(), checkfirst=True)

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add custom domain fields to tenants table.

Revision ID: 008_add_custom_domain_fields
Revises: 007_workspace_deletion_scheduled
Create Date: 2026-02-05

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008_add_custom_domain_fields"
down_revision: str | None = "007_workspace_deletion_scheduled"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the CustomDomainStatus enum type
    custom_domain_status = sa.Enum(
        "pending",
        "dns_verifying",
        "dns_verified",
        "ssl_provisioning",
        "active",
        "failed",
        name="customdomainstatus",
    )
    custom_domain_status.create(op.get_bind(), checkfirst=True)

    # Add custom domain columns to tenants table
    op.add_column(
        "tenants",
        sa.Column("custom_domain", sa.String(255), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_status",
            sa.Enum(
                "pending",
                "dns_verifying",
                "dns_verified",
                "ssl_provisioning",
                "active",
                "failed",
                name="customdomainstatus",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_ssl_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "tenants",
        sa.Column("custom_domain_error", sa.String(500), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "custom_domain_checked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Create indexes
    op.create_index(
        "ix_tenants_custom_domain",
        "tenants",
        ["custom_domain"],
        unique=True,
    )
    op.create_index(
        "ix_tenants_custom_domain_status",
        "tenants",
        ["custom_domain_status"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_tenants_custom_domain_status", table_name="tenants")
    op.drop_index("ix_tenants_custom_domain", table_name="tenants")

    # Drop columns
    op.drop_column("tenants", "custom_domain_checked_at")
    op.drop_column("tenants", "custom_domain_error")
    op.drop_column("tenants", "custom_domain_ssl_at")
    op.drop_column("tenants", "custom_domain_verified_at")
    op.drop_column("tenants", "custom_domain_status")
    op.drop_column("tenants", "custom_domain")

    # Drop enum type
    sa.Enum(name="customdomainstatus").drop(op.get_bind(), checkfirst=True)

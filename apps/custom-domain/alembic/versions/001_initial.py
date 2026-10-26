# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Initial migration - create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create domain_status enum
    domain_status = postgresql.ENUM(
        "pending",
        "dns_verifying",
        "dns_verified",
        "ssl_provisioning",
        "active",
        "failed",
        "suspended",
        "expired",
        "deprovisioning",
        name="domainstatus",
    )
    domain_status.create(op.get_bind())

    # Create authorized_clients table
    op.create_table(
        "authorized_clients",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("default_upstream_target", sa.String(length=500), nullable=True),
        sa.Column("default_cname_target", sa.String(length=255), nullable=True),
        sa.Column("default_nginx_template_id", sa.Integer(), nullable=True),
        sa.Column("max_domains", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="{}",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id"),
    )
    op.create_index(
        "ix_authorized_clients_client_id",
        "authorized_clients",
        ["client_id"],
        unique=True,
    )

    # Create nginx_templates table
    op.create_table(
        "nginx_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("http_template", sa.Text(), nullable=False),
        sa.Column("https_template", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, default=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "available_variables",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="[]",
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_nginx_templates_slug",
        "nginx_templates",
        ["slug"],
        unique=True,
    )

    # Create custom_domains table
    op.create_table(
        "custom_domains",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("owner_type", sa.String(length=50), nullable=False),
        sa.Column("upstream_target", sa.String(length=500), nullable=False),
        sa.Column("cname_target", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "dns_verifying",
                "dns_verified",
                "ssl_provisioning",
                "active",
                "failed",
                "suspended",
                "expired",
                "deprovisioning",
                name="domainstatus",
                create_type=False,
            ),
            nullable=False,
            default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, default=0),
        sa.Column("nginx_template_id", sa.Integer(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default="{}",
        ),
        sa.Column("dns_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ssl_provisioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ssl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
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
            ["nginx_template_id"],
            ["nginx_templates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_custom_domains_client_id",
        "custom_domains",
        ["client_id"],
    )
    op.create_index(
        "ix_custom_domains_owner_id",
        "custom_domains",
        ["owner_id"],
    )
    op.create_index(
        "ix_custom_domains_client_owner",
        "custom_domains",
        ["client_id", "owner_id"],
    )
    op.create_index(
        "ix_custom_domains_status",
        "custom_domains",
        ["status"],
    )
    op.create_index(
        "ix_custom_domains_deleted_at",
        "custom_domains",
        ["deleted_at"],
    )
    # Partial unique index for non-deleted domains
    op.execute("""
        CREATE UNIQUE INDEX ix_custom_domains_domain_unique
        ON custom_domains (domain)
        WHERE deleted_at IS NULL
    """)

    # Add foreign key for authorized_clients.default_nginx_template_id
    op.create_foreign_key(
        "fk_authorized_clients_nginx_template",
        "authorized_clients",
        "nginx_templates",
        ["default_nginx_template_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Drop foreign key
    op.drop_constraint(
        "fk_authorized_clients_nginx_template",
        "authorized_clients",
        type_="foreignkey",
    )

    # Drop tables
    op.drop_index("ix_custom_domains_domain_unique", table_name="custom_domains")
    op.drop_index("ix_custom_domains_deleted_at", table_name="custom_domains")
    op.drop_index("ix_custom_domains_status", table_name="custom_domains")
    op.drop_index("ix_custom_domains_client_owner", table_name="custom_domains")
    op.drop_index("ix_custom_domains_owner_id", table_name="custom_domains")
    op.drop_index("ix_custom_domains_client_id", table_name="custom_domains")
    op.drop_table("custom_domains")

    op.drop_index("ix_nginx_templates_slug", table_name="nginx_templates")
    op.drop_table("nginx_templates")

    op.drop_index("ix_authorized_clients_client_id", table_name="authorized_clients")
    op.drop_table("authorized_clients")

    # Drop enum
    domain_status = postgresql.ENUM(
        "pending",
        "dns_verifying",
        "dns_verified",
        "ssl_provisioning",
        "active",
        "failed",
        "suspended",
        "expired",
        "deprovisioning",
        name="domainstatus",
    )
    domain_status.drop(op.get_bind())

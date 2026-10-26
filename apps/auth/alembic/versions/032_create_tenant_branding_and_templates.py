# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create tenant branding and templates tables.

Revision ID: 032
Revises: 027
Create Date: 2026-01-27

This migration creates tables for tenant-specific branding (colors, logos, CSS)
and custom templates (Jinja2 templates stored in database).
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "032"
down_revision: str | None = "027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create tenant_branding table
    op.create_table(
        "tenant_branding",
        sa.Column("id", sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        # Logo and favicon
        sa.Column("logo_url", sa.String(2048), nullable=True),
        sa.Column("logo_dark_url", sa.String(2048), nullable=True),
        sa.Column("favicon_url", sa.String(2048), nullable=True),
        # Colors
        sa.Column("primary_color", sa.String(7), nullable=False, server_default="#007bff"),
        sa.Column("secondary_color", sa.String(7), nullable=False, server_default="#6c757d"),
        sa.Column("accent_color", sa.String(7), nullable=False, server_default="#28a745"),
        sa.Column("background_color", sa.String(7), nullable=False, server_default="#f5f5f5"),
        sa.Column("surface_color", sa.String(7), nullable=False, server_default="#ffffff"),
        sa.Column("text_color", sa.String(7), nullable=False, server_default="#333333"),
        sa.Column("text_muted_color", sa.String(7), nullable=False, server_default="#6c757d"),
        sa.Column("error_color", sa.String(7), nullable=False, server_default="#dc3545"),
        sa.Column("success_color", sa.String(7), nullable=False, server_default="#28a745"),
        # Typography
        sa.Column(
            "font_family",
            sa.String(255),
            nullable=False,
            server_default="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
        ),
        sa.Column("font_url", sa.String(2048), nullable=True),
        # Custom CSS/JS
        sa.Column("custom_css", sa.Text(), nullable=True),
        sa.Column("custom_js", sa.Text(), nullable=True),
        # Settings
        sa.Column("show_powered_by", sa.Boolean(), nullable=False, server_default="true"),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_branding_tenant_id"),
    )
    op.create_index("ix_tenant_branding_tenant_id", "tenant_branding", ["tenant_id"])

    # Create tenant_templates table
    op.create_table(
        "tenant_templates",
        sa.Column("id", sa.UUID(), nullable=False, default=uuid.uuid4),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("template_name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("description", sa.String(500), nullable=True),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "template_name", name="uq_tenant_templates_tenant_name"),
    )
    op.create_index("ix_tenant_templates_tenant_id", "tenant_templates", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_tenant_templates_tenant_id", table_name="tenant_templates")
    op.drop_table("tenant_templates")
    op.drop_index("ix_tenant_branding_tenant_id", table_name="tenant_branding")
    op.drop_table("tenant_branding")

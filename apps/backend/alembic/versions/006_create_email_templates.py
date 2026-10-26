# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create email_templates table for newsletter/email campaign system.

Revision ID: 006_create_email_templates
Revises: 005_add_system_prompts
Create Date: 2026-01-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_create_email_templates"
down_revision: str | None = "005_add_system_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create email_templates table."""
    op.create_table(
        "email_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject_template", sa.String(500), nullable=False, server_default=""),
        sa.Column("mjml_source", sa.Text(), nullable=False, server_default=""),
        sa.Column("html_compiled", sa.Text(), nullable=True),
        sa.Column("plain_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft", index=True),
        sa.Column(
            "variables",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop email_templates table."""
    op.drop_table("email_templates")

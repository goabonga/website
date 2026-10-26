# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add email templates table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-02

Creates email_templates table for storing MJML email templates. Templates are
owned by a client and their slug is unique per client.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    # Create email_templates table if not exists
    if not table_exists("email_templates"):
        op.create_table(
            "email_templates",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            # Owner
            sa.Column("client_id", sa.String(255), nullable=False),
            # Identification (unique per client)
            sa.Column("slug", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            # Content
            sa.Column("subject_template", sa.String(500), nullable=False),
            sa.Column("mjml_source", sa.Text(), nullable=False),
            sa.Column("html_compiled", sa.Text(), nullable=True),
            sa.Column("plain_text", sa.Text(), nullable=True),
            # Status
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            # Variables extracted from template
            sa.Column("variables", postgresql.ARRAY(sa.String()), nullable=True),
            # Metadata
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Primary key
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id", "slug", name="uq_email_templates_client_slug"),
        )

    # Create indexes if not exist
    if not index_exists("email_templates", "ix_email_templates_client_id"):
        op.create_index("ix_email_templates_client_id", "email_templates", ["client_id"])
    if not index_exists("email_templates", "ix_email_templates_slug"):
        op.create_index("ix_email_templates_slug", "email_templates", ["slug"])
    if not index_exists("email_templates", "ix_email_templates_status"):
        op.create_index("ix_email_templates_status", "email_templates", ["status"])


def downgrade() -> None:
    # Drop indexes and table
    op.drop_index("ix_email_templates_status", table_name="email_templates")
    op.drop_index("ix_email_templates_slug", table_name="email_templates")
    op.drop_index("ix_email_templates_client_id", table_name="email_templates")
    op.drop_table("email_templates")

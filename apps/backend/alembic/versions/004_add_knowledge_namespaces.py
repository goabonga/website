# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add knowledge namespaces table and namespace_id to knowledge_base.

Revision ID: 004_add_knowledge_namespaces
Revises: 003_add_conversation_summary
Create Date: 2026-01-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_add_knowledge_namespaces"
down_revision: str | None = "003_add_conversation_summary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create knowledge_namespaces table
    op.create_table(
        "knowledge_namespaces",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "required_scopes",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        sa.Column("is_public", sa.Boolean(), default=True, nullable=False),
        sa.Column("metadata", postgresql.JSONB(), default={}, nullable=False),
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

    # Add namespace_id column to knowledge_base
    op.add_column(
        "knowledge_base",
        sa.Column(
            "namespace_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_namespaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Create index on namespace_id
    op.create_index(
        "ix_knowledge_base_namespace_id",
        "knowledge_base",
        ["namespace_id"],
    )

    # Create a default "general" namespace for existing entries
    op.execute("""
        INSERT INTO knowledge_namespaces (slug, name, description, is_public, metadata)
        VALUES ('general', 'General', 'Default namespace for general knowledge', true, '{}')
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_knowledge_base_namespace_id", table_name="knowledge_base")

    # Drop namespace_id column
    op.drop_column("knowledge_base", "namespace_id")

    # Drop knowledge_namespaces table
    op.drop_table("knowledge_namespaces")

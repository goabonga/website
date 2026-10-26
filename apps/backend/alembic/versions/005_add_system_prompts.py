# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add system_prompts and system_prompt_versions tables.

Revision ID: 005_add_system_prompts
Revises: 004_add_knowledge_namespaces
Create Date: 2026-01-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_add_system_prompts"
down_revision: str | None = "004_add_knowledge_namespaces"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Default system prompt content
DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant. You provide accurate, helpful, and concise responses.

When responding:
- Be direct and helpful
- If you used information from the knowledge base, integrate it naturally
- If you don't know something, say so honestly
- Keep responses focused and relevant
"""


def upgrade() -> None:
    # Create system_prompts table
    op.create_table(
        "system_prompts",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "required_scopes",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
        sa.Column("is_default", sa.Boolean(), default=False, nullable=False),
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

    # Create system_prompt_versions table
    op.create_table(
        "system_prompt_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "prompt_id",
            sa.Integer(),
            sa.ForeignKey("system_prompts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), default={}, nullable=False),
        sa.Column("is_current", sa.Boolean(), default=False, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Create indexes
    op.create_index(
        "ix_system_prompt_versions_prompt_id",
        "system_prompt_versions",
        ["prompt_id"],
    )
    op.create_index(
        "ix_system_prompt_versions_prompt_current",
        "system_prompt_versions",
        ["prompt_id", "is_current"],
    )

    # Insert default system prompt
    op.execute("""
        INSERT INTO system_prompts (slug, name, description, is_default)
        VALUES ('default', 'Default Assistant', 'Default system prompt for all users', true)
    """)

    # Insert version 1 of the default prompt
    op.execute(f"""
        INSERT INTO system_prompt_versions (prompt_id, version, content, metadata, is_current)
        SELECT id, 1, $prompt${DEFAULT_SYSTEM_PROMPT}$prompt$, '{{}}'::jsonb, true
        FROM system_prompts
        WHERE slug = 'default'
    """)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_system_prompt_versions_prompt_current", table_name="system_prompt_versions")
    op.drop_index("ix_system_prompt_versions_prompt_id", table_name="system_prompt_versions")

    # Drop tables
    op.drop_table("system_prompt_versions")
    op.drop_table("system_prompts")

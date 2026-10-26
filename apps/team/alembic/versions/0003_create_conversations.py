# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""0003 create conversations, participants and messages

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("slug", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False, server_default="general"),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("extra", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "conversation_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", sa.String(50), nullable=False, server_default="message"),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("visibility", sa.String(50), nullable=False, server_default="public"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversation_participants")
    op.drop_table("conversations")

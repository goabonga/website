# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create email_campaigns and email_sends tables for campaign management.

Revision ID: 009_create_email_campaigns
Revises: 008_add_conversation_archived_at
Create Date: 2026-01-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_create_email_campaigns"
down_revision: str | None = "008_add_conversation_archived_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create email_campaigns and email_sends tables."""
    # Create email_campaigns table
    op.create_table(
        "email_campaigns",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("email_templates.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("contact_groups.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
            index=True,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_recipients", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicked_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bounced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        sa.Column("subject_override", sa.String(500), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("task_id", sa.String(255), nullable=True),
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

    # Create email_sends table
    op.create_table(
        "email_sends",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "campaign_id",
            sa.Integer(),
            sa.ForeignKey("email_campaigns.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("recipient_email", sa.String(255), nullable=False, index=True),
        sa.Column("recipient_name", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            index=True,
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("smtp_response", sa.String(500), nullable=True),
        sa.Column("message_id", sa.String(255), nullable=True, index=True),
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
    )


def downgrade() -> None:
    """Drop email_campaigns and email_sends tables."""
    op.drop_table("email_sends")
    op.drop_table("email_campaigns")

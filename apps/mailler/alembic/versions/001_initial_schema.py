# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Initial schema for Mailler.

Revision ID: 001
Revises:
Create Date: 2026-01-28

Creates emails and provider_stats tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create emails table
    op.create_table(
        "emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # Recipient
        sa.Column("to_email", sa.String(255), nullable=False),
        sa.Column("to_name", sa.String(255), nullable=True),
        # Sender
        sa.Column("from_email", sa.String(255), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("reply_to", sa.String(255), nullable=True),
        # Content
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("html_content", sa.Text(), nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        # Provider
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_message_id", sa.String(255), nullable=True),
        # Status
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        # Scheduling
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Metadata
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        # Request context
        sa.Column("client_id", sa.String(255), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        # Celery
        sa.Column("task_id", sa.String(255), nullable=True),
        # Primary key
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for emails table
    op.create_index("ix_emails_to_email", "emails", ["to_email"])
    op.create_index("ix_emails_provider", "emails", ["provider"])
    op.create_index("ix_emails_status", "emails", ["status"])
    op.create_index("ix_emails_scheduled_at", "emails", ["scheduled_at"])
    op.create_index("ix_emails_client_id", "emails", ["client_id"])
    op.create_index("ix_emails_user_id", "emails", ["user_id"])

    # Create provider_stats table
    op.create_table(
        "provider_stats",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bounced_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "provider", name="uq_provider_stats_date_provider"),
    )

    # Create indexes for provider_stats table
    op.create_index("ix_provider_stats_date", "provider_stats", ["date"])
    op.create_index("ix_provider_stats_provider", "provider_stats", ["provider"])


def downgrade() -> None:
    # Drop provider_stats indexes and table
    op.drop_index("ix_provider_stats_provider", table_name="provider_stats")
    op.drop_index("ix_provider_stats_date", table_name="provider_stats")
    op.drop_table("provider_stats")

    # Drop emails indexes and table
    op.drop_index("ix_emails_user_id", table_name="emails")
    op.drop_index("ix_emails_client_id", table_name="emails")
    op.drop_index("ix_emails_scheduled_at", table_name="emails")
    op.drop_index("ix_emails_status", table_name="emails")
    op.drop_index("ix_emails_provider", table_name="emails")
    op.drop_index("ix_emails_to_email", table_name="emails")
    op.drop_table("emails")

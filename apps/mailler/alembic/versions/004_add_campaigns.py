# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add email campaigns and sends tables.

Revision ID: 004
Revises: 003
Create Date: 2026-02-02

Creates email_campaigns and email_sends tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
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
    # Create email_campaigns table
    if not table_exists("email_campaigns"):
        op.create_table(
            "email_campaigns",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("client_id", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("template_id", sa.Integer(), nullable=True),
            sa.Column("group_id", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            # Scheduling
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            # Statistics
            sa.Column("total_recipients", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sent_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("delivered_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("opened_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("clicked_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bounced_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("complained_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
            # Email settings override
            sa.Column("from_name", sa.String(255), nullable=True),
            sa.Column("from_email", sa.String(255), nullable=True),
            sa.Column("reply_to", sa.String(255), nullable=True),
            sa.Column("provider", sa.String(50), nullable=True),
            sa.Column("subject_override", sa.String(500), nullable=True),
            # Metadata
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            # Celery
            sa.Column("task_id", sa.String(255), nullable=True),
            # Analytics
            sa.Column("analytics_campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("analytics_tracking_key", sa.String(64), nullable=True),
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
            # Primary key and foreign keys
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["template_id"], ["email_templates.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["group_id"], ["contact_groups.id"], ondelete="SET NULL"),
        )

    # Create indexes for email_campaigns
    if table_exists("email_campaigns"):
        if not index_exists("email_campaigns", "ix_email_campaigns_client_id"):
            op.create_index("ix_email_campaigns_client_id", "email_campaigns", ["client_id"])
        if not index_exists("email_campaigns", "ix_email_campaigns_status"):
            op.create_index("ix_email_campaigns_status", "email_campaigns", ["status"])
        if not index_exists("email_campaigns", "ix_email_campaigns_template_id"):
            op.create_index("ix_email_campaigns_template_id", "email_campaigns", ["template_id"])
        if not index_exists("email_campaigns", "ix_email_campaigns_group_id"):
            op.create_index("ix_email_campaigns_group_id", "email_campaigns", ["group_id"])
        if not index_exists("email_campaigns", "ix_email_campaigns_analytics_campaign_id"):
            op.create_index(
                "ix_email_campaigns_analytics_campaign_id",
                "email_campaigns",
                ["analytics_campaign_id"],
            )

    # Create email_sends table
    if not table_exists("email_sends"):
        op.create_table(
            "email_sends",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("campaign_id", sa.Integer(), nullable=False),
            sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
            # Recipient info
            sa.Column("recipient_email", sa.String(255), nullable=False),
            sa.Column("recipient_name", sa.String(255), nullable=True),
            # Status
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            # Timestamps
            sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("bounced_at", sa.DateTime(timezone=True), nullable=True),
            # Error tracking
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("smtp_response", sa.String(500), nullable=True),
            # Message ID
            sa.Column("message_id", sa.String(255), nullable=True),
            # Analytics
            sa.Column("analytics_pixel_key", sa.String(64), nullable=True),
            # Metadata
            sa.Column(
                "metadata",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Primary key and foreign keys
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["campaign_id"], ["email_campaigns.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="SET NULL"),
        )

    # Create indexes for email_sends
    if table_exists("email_sends"):
        if not index_exists("email_sends", "ix_email_sends_campaign_id"):
            op.create_index("ix_email_sends_campaign_id", "email_sends", ["campaign_id"])
        if not index_exists("email_sends", "ix_email_sends_contact_id"):
            op.create_index("ix_email_sends_contact_id", "email_sends", ["contact_id"])
        if not index_exists("email_sends", "ix_email_sends_recipient_email"):
            op.create_index("ix_email_sends_recipient_email", "email_sends", ["recipient_email"])
        if not index_exists("email_sends", "ix_email_sends_status"):
            op.create_index("ix_email_sends_status", "email_sends", ["status"])
        if not index_exists("email_sends", "ix_email_sends_message_id"):
            op.create_index("ix_email_sends_message_id", "email_sends", ["message_id"])


def downgrade() -> None:
    # Drop email_sends indexes and table
    op.drop_index("ix_email_sends_message_id", table_name="email_sends")
    op.drop_index("ix_email_sends_status", table_name="email_sends")
    op.drop_index("ix_email_sends_recipient_email", table_name="email_sends")
    op.drop_index("ix_email_sends_contact_id", table_name="email_sends")
    op.drop_index("ix_email_sends_campaign_id", table_name="email_sends")
    op.drop_table("email_sends")

    # Drop email_campaigns indexes and table
    op.drop_index("ix_email_campaigns_analytics_campaign_id", table_name="email_campaigns")
    op.drop_index("ix_email_campaigns_group_id", table_name="email_campaigns")
    op.drop_index("ix_email_campaigns_template_id", table_name="email_campaigns")
    op.drop_index("ix_email_campaigns_status", table_name="email_campaigns")
    op.drop_index("ix_email_campaigns_client_id", table_name="email_campaigns")
    op.drop_table("email_campaigns")

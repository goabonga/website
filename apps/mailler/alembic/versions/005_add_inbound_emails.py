# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add inbound emails and attachments tables.

Revision ID: 005
Revises: 004
Create Date: 2026-02-08

Creates inbound_emails and inbound_attachments tables for
receiving emails via IMAP and forwarding them as webhooks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
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
    # Create inbound_emails table
    if not table_exists("inbound_emails"):
        op.create_table(
            "inbound_emails",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            # Email identifiers
            sa.Column("message_id", sa.String(500), nullable=True),
            sa.Column("in_reply_to", sa.String(500), nullable=True),
            # Sender
            sa.Column("from_email", sa.String(255), nullable=False),
            sa.Column("from_name", sa.String(255), nullable=True),
            # Recipients (JSONB arrays of {Address, Name})
            sa.Column(
                "to_emails",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="[]",
            ),
            sa.Column(
                "cc_emails",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="[]",
            ),
            sa.Column("reply_to_email", sa.String(255), nullable=True),
            sa.Column("reply_to_name", sa.String(255), nullable=True),
            # Content
            sa.Column("subject", sa.String(500), nullable=False),
            sa.Column("html_body", sa.Text(), nullable=True),
            sa.Column("text_body", sa.Text(), nullable=True),
            # Headers
            sa.Column(
                "headers",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            # Metadata
            sa.Column("sent_at_date", sa.String(255), nullable=True),
            sa.Column("spam_score", sa.Float(), nullable=False, server_default="0.0"),
            # Processing status
            sa.Column(
                "status",
                sa.String(20),
                nullable=False,
                server_default="received",
            ),
            sa.Column("webhook_response_code", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            # IMAP reference
            sa.Column("imap_uid", sa.String(100), nullable=True),
            # Timestamps
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Primary key
            sa.PrimaryKeyConstraint("id"),
        )

    # Create indexes for inbound_emails
    if table_exists("inbound_emails"):
        if not index_exists("inbound_emails", "ix_inbound_emails_message_id"):
            op.create_index("ix_inbound_emails_message_id", "inbound_emails", ["message_id"])
        if not index_exists("inbound_emails", "ix_inbound_emails_from_email"):
            op.create_index("ix_inbound_emails_from_email", "inbound_emails", ["from_email"])
        if not index_exists("inbound_emails", "ix_inbound_emails_status"):
            op.create_index("ix_inbound_emails_status", "inbound_emails", ["status"])

    # Create inbound_attachments table
    if not table_exists("inbound_attachments"):
        op.create_table(
            "inbound_attachments",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "inbound_email_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            # File metadata
            sa.Column("filename", sa.String(255), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("content_length", sa.Integer(), nullable=False),
            sa.Column("content_id", sa.String(255), nullable=False, server_default=""),
            # Download token
            sa.Column(
                "download_token",
                postgresql.UUID(as_uuid=True),
                nullable=False,
                unique=True,
            ),
            # Storage
            sa.Column("file_path", sa.String(500), nullable=False),
            # Expiration
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            # Timestamps
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            # Keys
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["inbound_email_id"],
                ["inbound_emails.id"],
                ondelete="CASCADE",
            ),
        )

    # Create indexes for inbound_attachments
    if table_exists("inbound_attachments"):
        if not index_exists("inbound_attachments", "ix_inbound_attachments_inbound_email_id"):
            op.create_index(
                "ix_inbound_attachments_inbound_email_id",
                "inbound_attachments",
                ["inbound_email_id"],
            )
        if not index_exists("inbound_attachments", "ix_inbound_attachments_download_token"):
            op.create_index(
                "ix_inbound_attachments_download_token",
                "inbound_attachments",
                ["download_token"],
                unique=True,
            )


def downgrade() -> None:
    # Drop inbound_attachments indexes and table
    op.drop_index("ix_inbound_attachments_download_token", table_name="inbound_attachments")
    op.drop_index(
        "ix_inbound_attachments_inbound_email_id",
        table_name="inbound_attachments",
    )
    op.drop_table("inbound_attachments")

    # Drop inbound_emails indexes and table
    op.drop_index("ix_inbound_emails_status", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_from_email", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_message_id", table_name="inbound_emails")
    op.drop_table("inbound_emails")

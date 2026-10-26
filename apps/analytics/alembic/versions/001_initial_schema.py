# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create the sessions and events tables.

Revision ID: 001
Revises:
Create Date: 2025-01-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Analytics sessions table
    op.create_table(
        "analytics_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("country", sa.String(2), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("device_type", sa.String(20), nullable=True),
        sa.Column("browser", sa.String(50), nullable=True),
        sa.Column("browser_version", sa.String(20), nullable=True),
        sa.Column("os", sa.String(50), nullable=True),
        sa.Column("os_version", sa.String(20), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("utm_term", sa.String(100), nullable=True),
        sa.Column("utm_content", sa.String(100), nullable=True),
        sa.Column("landing_page", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_sessions_session_id",
        "analytics_sessions",
        ["session_id"],
        unique=True,
    )
    op.create_index(
        "ix_analytics_sessions_user_id",
        "analytics_sessions",
        ["user_id"],
    )
    op.create_index(
        "ix_analytics_sessions_first_seen",
        "analytics_sessions",
        ["first_seen"],
    )
    op.create_index(
        "ix_analytics_sessions_country",
        "analytics_sessions",
        ["country"],
    )
    op.create_index(
        "ix_analytics_sessions_utm_campaign",
        "analytics_sessions",
        ["utm_campaign"],
    )

    # Analytics events table
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_data", postgresql.JSONB(), nullable=True),
        sa.Column("page_url", sa.Text(), nullable=True),
        sa.Column("page_title", sa.String(255), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["analytics_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analytics_events_session_id",
        "analytics_events",
        ["session_id"],
    )
    op.create_index(
        "ix_analytics_events_event_type",
        "analytics_events",
        ["event_type"],
    )
    op.create_index(
        "ix_analytics_events_timestamp",
        "analytics_events",
        ["timestamp"],
    )
    op.create_index(
        "ix_analytics_events_type_timestamp",
        "analytics_events",
        ["event_type", "timestamp"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("analytics_events")
    op.drop_table("analytics_sessions")

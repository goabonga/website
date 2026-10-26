# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create the campaigns, pixels and pixel opens tables.

Revision ID: 002
Revises: 001
Create Date: 2025-01-21

Databases created by the original single "001" revision already own these
tables: each table is only created when it does not exist yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _existing_tables() -> set[str]:
    """Return the tables already present (none when rendering offline SQL)."""
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    """Upgrade schema."""
    existing = _existing_tables()

    if "analytics_campaigns" not in existing:
        op.create_table(
            "analytics_campaigns",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("tracking_key", sa.String(64), nullable=False),
            sa.Column("destination_url", sa.Text(), nullable=True),
            sa.Column("extra_data", postgresql.JSONB(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("click_count", sa.Integer(), nullable=False, default=0),
            sa.Column("unique_click_count", sa.Integer(), nullable=False, default=0),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_campaigns_tracking_key",
            "analytics_campaigns",
            ["tracking_key"],
            unique=True,
        )

    if "analytics_pixels" not in existing:
        op.create_table(
            "analytics_pixels",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("recipient_email", sa.String(255), nullable=True),
            sa.Column("recipient_id", sa.String(100), nullable=True),
            sa.Column("pixel_key", sa.String(64), nullable=False),
            sa.Column("extra_data", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("open_count", sa.Integer(), nullable=False, default=0),
            sa.ForeignKeyConstraint(
                ["campaign_id"],
                ["analytics_campaigns.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_pixels_campaign_id",
            "analytics_pixels",
            ["campaign_id"],
        )
        op.create_index(
            "ix_analytics_pixels_pixel_key",
            "analytics_pixels",
            ["pixel_key"],
            unique=True,
        )

    if "analytics_pixel_opens" not in existing:
        op.create_table(
            "analytics_pixel_opens",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("pixel_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ip_address", postgresql.INET(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("country", sa.String(2), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.ForeignKeyConstraint(
                ["pixel_id"],
                ["analytics_pixels.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_pixel_opens_pixel_id",
            "analytics_pixel_opens",
            ["pixel_id"],
        )
        op.create_index(
            "ix_analytics_pixel_opens_opened_at",
            "analytics_pixel_opens",
            ["opened_at"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("analytics_pixel_opens")
    op.drop_table("analytics_pixels")
    op.drop_table("analytics_campaigns")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create the campaign clicks table.

Revision ID: 003
Revises: 002
Create Date: 2025-01-21

Databases created by the original single "001" revision already own this
table: it is only created when it does not exist yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | Sequence[str] | None = "002"
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

    if "analytics_campaign_clicks" not in existing:
        op.create_table(
            "analytics_campaign_clicks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("campaign_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ip_address", postgresql.INET(), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
            sa.Column("country", sa.String(2), nullable=True),
            sa.Column("city", sa.String(100), nullable=True),
            sa.Column("referrer", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["campaign_id"],
                ["analytics_campaigns.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_analytics_campaign_clicks_campaign_id",
            "analytics_campaign_clicks",
            ["campaign_id"],
        )
        op.create_index(
            "ix_analytics_campaign_clicks_clicked_at",
            "analytics_campaign_clicks",
            ["clicked_at"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("analytics_campaign_clicks")

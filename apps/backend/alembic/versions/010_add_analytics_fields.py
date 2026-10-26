# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add analytics tracking fields to email campaigns and sends.

Revision ID: 010_add_analytics_fields
Revises: 009_create_email_campaigns
Create Date: 2026-01-25

This migration adds fields for integrating with the analytics service:
- email_campaigns.analytics_campaign_id: UUID reference to analytics campaign
- email_campaigns.analytics_tracking_key: Tracking key for link redirects
- email_sends.analytics_pixel_key: Pixel key for open tracking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_add_analytics_fields"
down_revision: str | None = "009_create_email_campaigns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add analytics tracking fields to email_campaigns
    op.add_column(
        "email_campaigns",
        sa.Column("analytics_campaign_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "email_campaigns",
        sa.Column("analytics_tracking_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_email_campaigns_analytics_campaign_id",
        "email_campaigns",
        ["analytics_campaign_id"],
    )

    # Add analytics pixel key to email_sends
    op.add_column(
        "email_sends",
        sa.Column("analytics_pixel_key", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    # Remove analytics pixel key from email_sends
    op.drop_column("email_sends", "analytics_pixel_key")

    # Remove analytics tracking fields from email_campaigns
    op.drop_index("ix_email_campaigns_analytics_campaign_id", "email_campaigns")
    op.drop_column("email_campaigns", "analytics_tracking_key")
    op.drop_column("email_campaigns", "analytics_campaign_id")

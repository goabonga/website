# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add complained_count to email_campaigns.

Revision ID: 011_add_complained_count
Revises: 010_add_analytics_fields
Create Date: 2026-01-26

This migration adds a complained_count field to track spam complaints
received via SES/SNS webhooks for each email campaign.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "011_add_complained_count"
down_revision: str | None = "010_add_analytics_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_campaigns",
        sa.Column("complained_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("email_campaigns", "complained_count")

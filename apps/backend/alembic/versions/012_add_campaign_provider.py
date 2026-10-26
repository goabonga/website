# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add provider field to email_campaigns.

Revision ID: 012_add_campaign_provider
Revises: 011_add_complained_count
Create Date: 2026-01-29

This migration adds a provider field to email_campaigns to allow
selecting the email provider (brevo, sendgrid, ses, protonmail)
per campaign. Email sending is now handled via the Mailler API.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012_add_campaign_provider"
down_revision: str | None = "011_add_complained_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_campaigns",
        sa.Column("provider", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_campaigns", "provider")

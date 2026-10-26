# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add homepage_url to oauth2_clients.

This migration adds homepage_url column to allow linking application names
in user settings to the application's homepage.

Revision ID: 033
Revises: 032
Create Date: 2026-01-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "033"
down_revision: str | None = "032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add homepage_url column (optional URL to application homepage)
    op.add_column(
        "oauth2_clients",
        sa.Column(
            "homepage_url",
            sa.String(2048),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth2_clients", "homepage_url")

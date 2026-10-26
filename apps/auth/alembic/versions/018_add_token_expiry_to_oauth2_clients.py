# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add custom token expiry settings to oauth2_clients.

This migration adds access_token_expiry_seconds and refresh_token_expiry_seconds
columns to allow per-client token expiry configuration.

Revision ID: 018
Revises: 017
Create Date: 2026-01-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add access_token_expiry_seconds column (NULL = use global config default)
    op.add_column(
        "oauth2_clients",
        sa.Column(
            "access_token_expiry_seconds",
            sa.Integer(),
            nullable=True,
        ),
    )

    # Add refresh_token_expiry_seconds column (NULL = use global config default)
    op.add_column(
        "oauth2_clients",
        sa.Column(
            "refresh_token_expiry_seconds",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth2_clients", "refresh_token_expiry_seconds")
    op.drop_column("oauth2_clients", "access_token_expiry_seconds")

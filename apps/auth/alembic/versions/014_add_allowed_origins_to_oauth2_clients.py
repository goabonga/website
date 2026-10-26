# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add allowed_origins to oauth2_clients table.

Revision ID: 014
Revises: 013
Create Date: 2024-12-31

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add allowed_origins column for CORS configuration
    op.add_column(
        "oauth2_clients",
        sa.Column(
            "allowed_origins",
            postgresql.ARRAY(sa.String(length=2048)),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth2_clients", "allowed_origins")

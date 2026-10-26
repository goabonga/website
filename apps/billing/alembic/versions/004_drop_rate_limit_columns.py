# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drop unused rate_limit columns from saas_apps.

Revision ID: 004
Revises: 003
Create Date: 2026-02-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("saas_apps", "rate_limit_requests")
    op.drop_column("saas_apps", "rate_limit_window")


def downgrade() -> None:
    op.add_column(
        "saas_apps",
        sa.Column("rate_limit_requests", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "saas_apps",
        sa.Column("rate_limit_window", sa.Integer(), nullable=False, server_default="60"),
    )

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add deleted_at column to customers for soft delete.

Revision ID: 003
Revises: 002
Create Date: 2026-02-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add deleted_at column for soft delete
    op.add_column(
        "customers",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Add index for efficient filtering of active customers
    op.create_index("ix_customers_deleted_at", "customers", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_customers_deleted_at", table_name="customers")
    op.drop_column("customers", "deleted_at")

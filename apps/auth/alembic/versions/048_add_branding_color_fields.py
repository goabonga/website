# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add border_color, warning_color, info_color to tenant_branding.

Revision ID: 048
Revises: 045
Create Date: 2026-02-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "048"
down_revision: str | None = "045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_branding",
        sa.Column("border_color", sa.String(7), nullable=False, server_default="#0f3460"),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("warning_color", sa.String(7), nullable=False, server_default="#fdcb6e"),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("info_color", sa.String(7), nullable=False, server_default="#74b9ff"),
    )


def downgrade() -> None:
    op.drop_column("tenant_branding", "info_color")
    op.drop_column("tenant_branding", "warning_color")
    op.drop_column("tenant_branding", "border_color")

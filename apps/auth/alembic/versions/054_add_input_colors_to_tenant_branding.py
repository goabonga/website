# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add input-specific color columns to tenant_branding.

Revision ID: 054
Revises: 049
Create Date: 2026-03-29

Adds 5 nullable color columns for per-tenant input field styling:
input_background_color, input_focus_background_color, input_border_color,
input_focus_border_color, input_text_color. When NULL, templates fall back
to the existing general colors (background_color, border_color, etc.).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "054"
down_revision: str | None = "049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_branding",
        sa.Column("input_background_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("input_focus_background_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("input_border_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("input_focus_border_color", sa.String(7), nullable=True),
    )
    op.add_column(
        "tenant_branding",
        sa.Column("input_text_color", sa.String(7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_branding", "input_text_color")
    op.drop_column("tenant_branding", "input_focus_border_color")
    op.drop_column("tenant_branding", "input_border_color")
    op.drop_column("tenant_branding", "input_focus_background_color")
    op.drop_column("tenant_branding", "input_background_color")

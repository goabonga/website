# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the owning client to nginx templates.

Revision ID: 002_template_owner
Revises: 001_initial
Create Date: 2026-01-01 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_template_owner"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "nginx_templates",
        sa.Column(
            "client_id",
            sa.String(length=255),
            nullable=True,
            comment="Owning client; NULL for a shared template",
        ),
    )
    op.create_index("ix_nginx_templates_client_id", "nginx_templates", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_nginx_templates_client_id", table_name="nginx_templates")
    op.drop_column("nginx_templates", "client_id")

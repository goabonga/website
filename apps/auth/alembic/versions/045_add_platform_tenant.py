# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the is_platform flag to tenants.

Revision ID: 045
Revises: 044
Create Date: 2024-02-03

Only the schema changes here. The platform tenant row (slug, display name, branding),
the registration of the existing users on it and their memberships are not done by a
migration: no row, hence no deployment value, lives in the migrations.
"""

import sqlalchemy as sa
from alembic import op

revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("is_platform", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_tenants_is_platform", "tenants", ["is_platform"])


def downgrade() -> None:
    op.drop_index("ix_tenants_is_platform", table_name="tenants")
    op.drop_column("tenants", "is_platform")

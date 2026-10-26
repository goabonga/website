# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create user_profiles table.

Revision ID: 013
Revises: 012
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # Standard OIDC claims
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("given_name", sa.String(length=255), nullable=True),
        sa.Column("family_name", sa.String(length=255), nullable=True),
        sa.Column("middle_name", sa.String(length=255), nullable=True),
        sa.Column("nickname", sa.String(length=255), nullable=True),
        sa.Column("preferred_username", sa.String(length=255), nullable=True),
        sa.Column("profile_url", sa.String(length=2048), nullable=True),
        sa.Column("picture_url", sa.String(length=2048), nullable=True),
        sa.Column("website", sa.String(length=2048), nullable=True),
        sa.Column("gender", sa.String(length=50), nullable=True),
        sa.Column("birthdate", sa.String(length=10), nullable=True),
        sa.Column("zoneinfo", sa.String(length=50), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=True),
        # Address claims
        sa.Column("address_formatted", sa.Text(), nullable=True),
        sa.Column("address_street", sa.String(length=500), nullable=True),
        sa.Column("address_locality", sa.String(length=255), nullable=True),
        sa.Column("address_region", sa.String(length=255), nullable=True),
        sa.Column("address_postal_code", sa.String(length=50), nullable=True),
        sa.Column("address_country", sa.String(length=100), nullable=True),
        # Phone
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("phone_number_verified", sa.Boolean(), nullable=False, server_default="false"),
        # Timestamps
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_profiles_user_id", "user_profiles", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_profiles_user_id", table_name="user_profiles")
    op.drop_table("user_profiles")

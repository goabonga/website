# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create pairwise_subjects table.

Stores per-tenant pairwise subject identifiers so that each (user, tenant) pair
gets a unique, opaque ``sub`` value in tokens. This prevents cross-tenant user
tracking.

Revision ID: 057
Revises: 054
Create Date: 2026-03-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "057"
down_revision: str | None = "054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pairwise_subjects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("sub_value", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pairwise_subjects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_pairwise_subjects_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pairwise_subjects")),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_pairwise_user_tenant"),
    )

    # Indexes for fast lookups
    op.create_index(
        op.f("ix_pairwise_subjects_user_id"),
        "pairwise_subjects",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pairwise_subjects_tenant_id"),
        "pairwise_subjects",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pairwise_subjects_sub_value"),
        "pairwise_subjects",
        ["sub_value"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pairwise_subjects_sub_value"),
        table_name="pairwise_subjects",
    )
    op.drop_index(
        op.f("ix_pairwise_subjects_tenant_id"),
        table_name="pairwise_subjects",
    )
    op.drop_index(
        op.f("ix_pairwise_subjects_user_id"),
        table_name="pairwise_subjects",
    )
    op.drop_table("pairwise_subjects")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create MFA email codes table.

Revision ID: 007
Revises: 006
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mfa_email_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_mfa_email_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_email_codes")),
    )
    op.create_index(
        op.f("ix_mfa_email_codes_user_id"),
        "mfa_email_codes",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mfa_email_codes_code_hash"),
        "mfa_email_codes",
        ["code_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_mfa_email_codes_code_hash"), table_name="mfa_email_codes")
    op.drop_index(op.f("ix_mfa_email_codes_user_id"), table_name="mfa_email_codes")
    op.drop_table("mfa_email_codes")

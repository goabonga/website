# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create MFA tables.

Revision ID: 006
Revises: 005
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create user_mfas table
    op.create_table(
        "user_mfas",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("totp_secret_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, default=False),
        sa.Column("totp_enabled_at", sa.DateTime(timezone=True), nullable=True),
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
            name=op.f("fk_user_mfas_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_mfas")),
    )
    op.create_index(
        op.f("ix_user_mfas_user_id"),
        "user_mfas",
        ["user_id"],
        unique=True,
    )

    # Create mfa_backup_codes table
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_mfa_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
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
            ["user_mfa_id"],
            ["user_mfas.id"],
            name=op.f("fk_mfa_backup_codes_user_mfa_id_user_mfas"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mfa_backup_codes")),
    )
    op.create_index(
        op.f("ix_mfa_backup_codes_user_mfa_id"),
        "mfa_backup_codes",
        ["user_mfa_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mfa_backup_codes_code_hash"),
        "mfa_backup_codes",
        ["code_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_mfa_backup_codes_code_hash"), table_name="mfa_backup_codes")
    op.drop_index(op.f("ix_mfa_backup_codes_user_mfa_id"), table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
    op.drop_index(op.f("ix_user_mfas_user_id"), table_name="user_mfas")
    op.drop_table("user_mfas")

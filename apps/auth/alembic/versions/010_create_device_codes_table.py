# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create device_codes table.

Revision ID: 010
Revises: 009
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create device_codes table
    op.create_table(
        "device_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_code", sa.String(length=16), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("verification_uri", sa.String(length=2048), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
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
            ["client_id"],
            ["oauth2_clients.id"],
            name=op.f("fk_device_codes_client_id_oauth2_clients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_device_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_codes")),
    )
    op.create_index(
        op.f("ix_device_codes_device_code_hash"),
        "device_codes",
        ["device_code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_device_codes_user_code"),
        "device_codes",
        ["user_code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_device_codes_client_id"),
        "device_codes",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_device_codes_user_id"),
        "device_codes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_device_codes_user_id"), table_name="device_codes")
    op.drop_index(op.f("ix_device_codes_client_id"), table_name="device_codes")
    op.drop_index(op.f("ix_device_codes_user_code"), table_name="device_codes")
    op.drop_index(op.f("ix_device_codes_device_code_hash"), table_name="device_codes")
    op.drop_table("device_codes")

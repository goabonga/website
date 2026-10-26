# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create VPN certificates table.

Revision ID: 001
Revises:
Create Date: 2026-01-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create vpn_certificates table
    op.create_table(
        "vpn_certificates",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=False),
        sa.Column("common_name", sa.String(length=255), nullable=False),
        sa.Column("not_before", sa.DateTime(timezone=True), nullable=False),
        sa.Column("not_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=True),
        sa.Column("scopes", ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("assigned_routes", ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vpn_certificates")),
        sa.UniqueConstraint("serial_number", name=op.f("uq_vpn_certificates_serial_number")),
    )
    op.create_index(
        op.f("ix_vpn_certificates_user_id"),
        "vpn_certificates",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vpn_certificates_serial_number"),
        "vpn_certificates",
        ["serial_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vpn_certificates_common_name"),
        "vpn_certificates",
        ["common_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vpn_certificates_not_after"),
        "vpn_certificates",
        ["not_after"],
        unique=False,
    )
    op.create_index(
        op.f("ix_vpn_certificates_revoked_at"),
        "vpn_certificates",
        ["revoked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vpn_certificates_revoked_at"), table_name="vpn_certificates")
    op.drop_index(op.f("ix_vpn_certificates_not_after"), table_name="vpn_certificates")
    op.drop_index(op.f("ix_vpn_certificates_common_name"), table_name="vpn_certificates")
    op.drop_index(op.f("ix_vpn_certificates_serial_number"), table_name="vpn_certificates")
    op.drop_index(op.f("ix_vpn_certificates_user_id"), table_name="vpn_certificates")
    op.drop_table("vpn_certificates")

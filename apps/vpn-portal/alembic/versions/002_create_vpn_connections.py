# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create VPN connections table.

Revision ID: 002
Revises: 001
Create Date: 2026-01-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vpn_connections",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("certificate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_ip", sa.String(length=45), nullable=False),
        sa.Column("client_ip", sa.String(length=45), nullable=False),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_sent", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.ForeignKeyConstraint(
            ["certificate_id"],
            ["vpn_certificates.id"],
            name=op.f("fk_vpn_connections_certificate_id_vpn_certificates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_vpn_connections")),
    )
    op.create_index(
        op.f("ix_vpn_connections_certificate_id"),
        "vpn_connections",
        ["certificate_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_vpn_connections_certificate_id"), table_name="vpn_connections")
    op.drop_table("vpn_connections")

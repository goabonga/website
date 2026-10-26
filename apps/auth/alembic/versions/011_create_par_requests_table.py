# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create par_requests table.

Revision ID: 011
Revises: 010
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create par_requests table
    op.create_table(
        "par_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("request_uri", sa.String(length=128), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("response_type", sa.String(length=32), nullable=False),
        sa.Column("redirect_uri", sa.String(length=2048), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("code_challenge", sa.String(length=128), nullable=True),
        sa.Column("code_challenge_method", sa.String(length=16), nullable=True),
        sa.Column("nonce", sa.String(length=255), nullable=True),
        sa.Column("prompt", sa.String(length=64), nullable=True),
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
            ["client_id"],
            ["oauth2_clients.id"],
            name=op.f("fk_par_requests_client_id_oauth2_clients"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_par_requests")),
    )
    op.create_index(
        op.f("ix_par_requests_request_uri"),
        "par_requests",
        ["request_uri"],
        unique=True,
    )
    op.create_index(
        op.f("ix_par_requests_client_id"),
        "par_requests",
        ["client_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_par_requests_client_id"), table_name="par_requests")
    op.drop_index(op.f("ix_par_requests_request_uri"), table_name="par_requests")
    op.drop_table("par_requests")

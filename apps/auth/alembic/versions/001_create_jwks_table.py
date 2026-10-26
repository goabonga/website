# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create jwks table.

Revision ID: 001
Revises:
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jwks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kid", sa.String(length=64), nullable=False),
        sa.Column("kty", sa.String(length=8), nullable=False),
        sa.Column("alg", sa.String(length=16), nullable=False),
        sa.Column("use", sa.String(length=8), nullable=False),
        sa.Column("private_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jwks")),
        sa.UniqueConstraint("kid", name=op.f("uq_jwks_kid")),
    )
    op.create_index(op.f("ix_kid"), "jwks", ["kid"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kid"), table_name="jwks")
    op.drop_table("jwks")

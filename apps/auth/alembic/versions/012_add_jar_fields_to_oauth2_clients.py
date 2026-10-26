# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add JAR fields to oauth2_clients table.

Revision ID: 012
Revises: 011
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add JAR (JWT Authorization Request) fields to oauth2_clients
    op.add_column(
        "oauth2_clients",
        sa.Column("jwks_uri", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "oauth2_clients",
        sa.Column(
            "request_object_signing_alg",
            sa.String(length=16),
            nullable=True,
            server_default="RS256",
        ),
    )


def downgrade() -> None:
    op.drop_column("oauth2_clients", "request_object_signing_alg")
    op.drop_column("oauth2_clients", "jwks_uri")

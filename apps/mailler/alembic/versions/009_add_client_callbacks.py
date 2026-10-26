# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the status callbacks of the authorized clients.

Revision ID: 009
Revises: 008
Create Date: 2026-10-26

Adds the callback URL and the secret signing the notifications to
authorized_clients.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("authorized_clients")}
    if "callback_url" not in existing:
        op.add_column(
            "authorized_clients", sa.Column("callback_url", sa.String(1000), nullable=True)
        )
    if "callback_secret" not in existing:
        op.add_column(
            "authorized_clients", sa.Column("callback_secret", sa.String(255), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("authorized_clients") as batch:
        batch.drop_column("callback_secret")
        batch.drop_column("callback_url")

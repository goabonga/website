# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the sending limits of the authorized clients.

Revision ID: 007
Revises: 006
Create Date: 2026-10-26

Adds the per-minute rate limit and the daily quota to authorized_clients, and
an index on emails (client_id, created_at) that the limit checks count with.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMAILS_INDEX = "ix_emails_client_id_created_at"


def _columns(table_name: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    existing = _columns("authorized_clients")
    if "rate_limit_per_minute" not in existing:
        op.add_column(
            "authorized_clients", sa.Column("rate_limit_per_minute", sa.Integer(), nullable=True)
        )
    if "daily_quota" not in existing:
        op.add_column("authorized_clients", sa.Column("daily_quota", sa.Integer(), nullable=True))

    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("emails")}
    if EMAILS_INDEX not in indexes:
        op.create_index(EMAILS_INDEX, "emails", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index(EMAILS_INDEX, table_name="emails")
    with op.batch_alter_table("authorized_clients") as batch:
        batch.drop_column("daily_quota")
        batch.drop_column("rate_limit_per_minute")

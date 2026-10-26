# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the idempotency key of emails.

Revision ID: 008
Revises: 007
Create Date: 2026-10-26

Adds emails.idempotency_key and makes it unique per client, so that a request
repeated with the same Idempotency-Key header does not create a second email.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "uq_emails_client_idempotency"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "idempotency_key" not in {c["name"] for c in inspector.get_columns("emails")}:
        op.add_column("emails", sa.Column("idempotency_key", sa.String(255), nullable=True))
    if CONSTRAINT not in {c["name"] for c in inspector.get_unique_constraints("emails")}:
        with op.batch_alter_table("emails") as batch:
            batch.create_unique_constraint(CONSTRAINT, ["client_id", "idempotency_key"])


def downgrade() -> None:
    with op.batch_alter_table("emails") as batch:
        batch.drop_constraint(CONSTRAINT, type_="unique")
        batch.drop_column("idempotency_key")

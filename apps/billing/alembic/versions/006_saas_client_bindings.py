# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Bind OAuth clients to SaaS applications.

Adds ``saas_client_bindings``: the list of OAuth clients allowed to act on
each SaaS application. The table starts empty: bindings are created with the
admin API or the ``billing-admin`` command.

Revision ID: 006
Revises: 005
Create Date: 2026-03-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "saas_client_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "saas_app_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("saas_apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("saas_app_id", "client_id", name="uq_binding_saas_client"),
    )
    op.create_index("ix_saas_client_bindings_client", "saas_client_bindings", ["client_id"])


def downgrade() -> None:
    op.drop_table("saas_client_bindings")

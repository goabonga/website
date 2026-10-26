# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add is_default flag to tenant_roles.

Revision ID: 060
Revises: 059
Create Date: 2026-04-19

Flags the role assigned automatically on self-register and IdP
auto-provisioning. Backfills existing tenants: the role named ``member``
inherits the flag to preserve current behaviour. A partial unique index
ensures at most one default role per tenant.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "060"
down_revision: str | None = "059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_roles",
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Preserve current behaviour: "member" is today's implicit default.
    op.execute(
        sa.text(
            """
            UPDATE tenant_roles
            SET is_default = true
            WHERE name = 'member'
            """
        )
    )

    # Enforce at most one default per tenant.
    op.create_index(
        "uq_tenant_roles_default",
        "tenant_roles",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_tenant_roles_default", table_name="tenant_roles")
    op.drop_column("tenant_roles", "is_default")

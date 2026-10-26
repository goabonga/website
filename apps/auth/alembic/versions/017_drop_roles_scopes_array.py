# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drop the scopes ARRAY column of roles: role_scopes is the only source.

The role/scope associations are rows of ``role_scopes``. Nothing is copied from
the array: the roles and their scopes are rows of ``role_scopes``. A migration
inserts no row, so no deployment value is written in the migrations.

Revision ID: 017
Revises: 016
Create Date: 2026-01-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "017"
down_revision: str | None = "016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("roles", "scopes")


def downgrade() -> None:
    # Step 1: Re-add the scopes ARRAY column
    op.add_column(
        "roles",
        sa.Column(
            "scopes",
            sa.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
    )

    conn = op.get_bind()

    # Step 2: Populate scopes array from role_scopes relationship
    roles_result = conn.execute(sa.text("SELECT id FROM roles"))
    roles = roles_result.fetchall()

    for (role_id,) in roles:
        # Get all scope names for this role
        scopes_result = conn.execute(
            sa.text(
                """
                SELECT s.name FROM scopes s
                JOIN role_scopes rs ON rs.scope_id = s.id
                WHERE rs.role_id = :role_id
                """
            ),
            {"role_id": role_id},
        )
        scope_names = [row[0] for row in scopes_result.fetchall()]

        # Update the role with the scopes array
        conn.execute(
            sa.text("UPDATE roles SET scopes = :scopes WHERE id = :id"),
            {"id": role_id, "scopes": scope_names},
        )

    # Step 3: Clear role_scopes table (data is now in the array)
    conn.execute(sa.text("DELETE FROM role_scopes"))

    # Step 4: Remove the server_default
    op.alter_column("roles", "scopes", server_default=None)

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create the scopes and role_scopes tables.

The migrations create no row: they only build the schema.

Revision ID: 016
Revises: 015
Create Date: 2026-01-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create scopes table
    op.create_table(
        "scopes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("resource", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False, server_default="admin"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scopes")),
        sa.UniqueConstraint("name", name=op.f("uq_scopes_name")),
    )
    op.create_index(op.f("ix_scopes_name"), "scopes", ["name"], unique=False)
    op.create_index(op.f("ix_scopes_resource"), "scopes", ["resource"], unique=False)
    op.create_index(op.f("ix_scopes_category"), "scopes", ["category"], unique=False)

    # Create role_scopes association table
    op.create_table(
        "role_scopes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role_id", sa.UUID(), nullable=False),
        sa.Column("scope_id", sa.UUID(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_role_scopes")),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["roles.id"],
            name=op.f("fk_role_scopes_role_id_roles"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scope_id"],
            ["scopes.id"],
            name=op.f("fk_role_scopes_scope_id_scopes"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("role_id", "scope_id", name="uq_role_scopes_role_id_scope_id"),
    )
    op.create_index(op.f("ix_role_scopes_role_id"), "role_scopes", ["role_id"], unique=False)
    op.create_index(op.f("ix_role_scopes_scope_id"), "role_scopes", ["scope_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_role_scopes_scope_id"), table_name="role_scopes")
    op.drop_index(op.f("ix_role_scopes_role_id"), table_name="role_scopes")
    op.drop_table("role_scopes")

    op.drop_index(op.f("ix_scopes_category"), table_name="scopes")
    op.drop_index(op.f("ix_scopes_resource"), table_name="scopes")
    op.drop_index(op.f("ix_scopes_name"), table_name="scopes")
    op.drop_table("scopes")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add tenant custom roles with scopes.

This migration:
1. Creates tenant_roles table
2. For each existing tenant, creates default roles (Owner, Admin, Member)
3. Adds role_id column to tenant_members
4. Migrates existing role assignments from enum to new role references
5. Makes role_id NOT NULL and drops old role enum column

Revision ID: 049
Revises: 048
Create Date: 2026-02-06
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "049"
down_revision: str | None = "048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Default role configurations
DEFAULT_ROLES = {
    "owner": {
        "display_name": "Owner",
        "description": "Full control over the organization, including managing other owners",
        "scopes": ["*"],
        "display_order": 0,
    },
    "admin": {
        "display_name": "Admin",
        "description": "Can manage members, IdPs, branding, and templates (except owner roles)",
        "scopes": [
            "members:*",
            "settings:read",
            "roles:read",
            "idp:*",
            "branding:*",
            "templates:*",
            "trust:read",
        ],
        "display_order": 1,
    },
    "member": {
        "display_name": "Member",
        "description": "Basic access to organization resources",
        "scopes": ["members:read"],
        "display_order": 2,
    },
}


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Create tenant_roles table
    op.create_table(
        "tenant_roles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(100)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_roles")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_roles_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_roles_tenant_name"),
    )
    op.create_index(op.f("ix_tenant_roles_tenant_id"), "tenant_roles", ["tenant_id"])

    # Step 2: Create default roles for each existing tenant
    tenants = conn.execute(sa.text("SELECT id FROM tenants")).fetchall()
    role_mapping: dict[str, dict[str, uuid.UUID]] = {}  # tenant_id -> {role_name: role_id}

    for (tenant_id,) in tenants:
        tenant_id_str = str(tenant_id)
        role_mapping[tenant_id_str] = {}

        for role_name, role_def in DEFAULT_ROLES.items():
            role_id = uuid.uuid4()
            role_mapping[tenant_id_str][role_name] = role_id

            conn.execute(
                sa.text("""
                    INSERT INTO tenant_roles
                    (id, tenant_id, name, display_name, description, scopes, is_system, display_order, created_at, updated_at)
                    VALUES (:id, :tenant_id, :name, :display_name, :description, :scopes, true, :display_order, NOW(), NOW())
                """),
                {
                    "id": role_id,
                    "tenant_id": tenant_id,
                    "name": role_name,
                    "display_name": role_def["display_name"],
                    "description": role_def["description"],
                    "scopes": role_def["scopes"],
                    "display_order": role_def["display_order"],
                },
            )

    # Step 3: Add role_id column to tenant_members (nullable initially)
    op.add_column("tenant_members", sa.Column("role_id", sa.UUID(), nullable=True))

    # Step 4: Migrate existing role assignments
    members = conn.execute(sa.text("SELECT id, tenant_id, role FROM tenant_members")).fetchall()

    for member_id, tenant_id, old_role in members:
        tenant_id_str = str(tenant_id)
        if tenant_id_str in role_mapping and old_role:
            # Map old enum value to new role_id
            new_role_id = role_mapping[tenant_id_str].get(old_role.lower())
            if new_role_id:
                conn.execute(
                    sa.text("UPDATE tenant_members SET role_id = :role_id WHERE id = :id"),
                    {"role_id": new_role_id, "id": member_id},
                )

    # Step 5: Make role_id NOT NULL and add foreign key constraint
    op.alter_column("tenant_members", "role_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_tenant_members_role_id_tenant_roles"),
        "tenant_members",
        "tenant_roles",
        ["role_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_tenant_members_role_id"), "tenant_members", ["role_id"])

    # Step 6: Drop old role enum column
    op.drop_column("tenant_members", "role")

    # Step 7: Drop the old enum type
    op.execute("DROP TYPE IF EXISTS tenantrole")


def downgrade() -> None:
    conn = op.get_bind()

    # Step 1: Re-create the enum type
    op.execute("CREATE TYPE tenantrole AS ENUM ('owner', 'admin', 'member')")

    # Step 2: Add role column back
    op.add_column(
        "tenant_members",
        sa.Column(
            "role",
            postgresql.ENUM("owner", "admin", "member", name="tenantrole", create_type=False),
            nullable=True,
        ),
    )

    # Step 3: Migrate role_id back to enum
    members = conn.execute(
        sa.text("""
            SELECT tm.id, tr.name
            FROM tenant_members tm
            JOIN tenant_roles tr ON tm.role_id = tr.id
        """)
    ).fetchall()

    for member_id, role_name in members:
        # Map back to enum value (only system roles)
        if role_name in ("owner", "admin", "member"):
            conn.execute(
                sa.text("UPDATE tenant_members SET role = :role WHERE id = :id"),
                {"role": role_name, "id": member_id},
            )
        else:
            # Custom roles default to member
            conn.execute(
                sa.text("UPDATE tenant_members SET role = 'member' WHERE id = :id"),
                {"id": member_id},
            )

    # Step 4: Make role NOT NULL
    op.alter_column("tenant_members", "role", nullable=False, server_default="member")

    # Step 5: Drop role_id column and index
    op.drop_constraint(
        op.f("fk_tenant_members_role_id_tenant_roles"),
        "tenant_members",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_tenant_members_role_id"), "tenant_members")
    op.drop_column("tenant_members", "role_id")

    # Step 6: Drop tenant_roles table
    op.drop_index(op.f("ix_tenant_roles_tenant_id"), "tenant_roles")
    op.drop_table("tenant_roles")

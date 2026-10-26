# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""GitHub-like ownership model migration.

This migration transforms the data model from pure tenant-based ownership
to a GitHub-like model where:
- Collections can be owned by users (personal) or organizations
- Organizations are for Enterprise plan only
- Users can invite collaborators to their personal collections

Revision ID: 003_github_ownership
Revises: 002_multi_tenant_web
Create Date: 2025-01-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_github_ownership"
down_revision: str | None = "002_multi_tenant_web"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Create new enums (check if they exist first)
    # Check ownertype
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'ownertype'"))
    if not result.fetchone():
        op.execute("CREATE TYPE ownertype AS ENUM ('user', 'organization')")

    # Check collaboratorpermission
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'collaboratorpermission'"))
    if not result.fetchone():
        op.execute("CREATE TYPE collaboratorpermission AS ENUM ('read', 'write', 'admin')")

    # Check invitationstatus (for collection invitations)
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'invitationstatus'"))
    if not result.fetchone():
        op.execute(
            "CREATE TYPE invitationstatus AS ENUM ('pending', 'accepted', 'expired', 'revoked')"
        )

    # 2. Create user_plans table for personal account quotas
    # Check if table exists
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'user_plans'")
    )
    if not result.fetchone():
        # Use raw SQL to avoid SQLAlchemy trying to create the plantype enum
        op.execute("""
            CREATE TABLE user_plans (
                user_id UUID NOT NULL PRIMARY KEY,
                plan plantype NOT NULL DEFAULT 'FREE',
                settings JSONB NOT NULL DEFAULT '{}',
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """)
        op.create_index("ix_user_plans_plan", "user_plans", ["plan"])

    # 3. Add polymorphic ownership columns to collections (if not exist)
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'collections' AND column_name = 'owner_type'"
        )
    )
    if not result.fetchone():
        # First add as nullable
        op.execute("ALTER TABLE collections ADD COLUMN owner_type ownertype")
        op.execute("ALTER TABLE collections ADD COLUMN owner_id UUID")

        # 4. Migrate existing data: tenant_id -> owner_type='organization', owner_id=tenant_id
        op.execute("""
            UPDATE collections
            SET owner_type = 'organization',
                owner_id = tenant_id
            WHERE tenant_id IS NOT NULL
        """)

        # 5. Make columns non-nullable after migration
        op.execute("ALTER TABLE collections ALTER COLUMN owner_type SET NOT NULL")
        op.execute("ALTER TABLE collections ALTER COLUMN owner_id SET NOT NULL")

        # 6. Create index for owner lookups
        op.create_index("ix_collections_owner", "collections", ["owner_type", "owner_id"])

        # 7. Create new unique constraint for polymorphic ownership
        op.create_unique_constraint(
            "uq_collection_owner_slug",
            "collections",
            ["owner_type", "owner_id", "slug"],
        )

    # 8. Modify tenant_id FK to allow NULL and SET NULL on delete
    # Check current constraint
    result = conn.execute(
        sa.text("""
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'collections_tenant_id_fkey'
        AND table_name = 'collections'
    """)
    )
    if result.fetchone():
        # Drop existing FK constraint
        op.drop_constraint("collections_tenant_id_fkey", "collections", type_="foreignkey")
        # Make column nullable
        op.alter_column("collections", "tenant_id", nullable=True)
        # Recreate FK with SET NULL on delete
        op.create_foreign_key(
            "collections_tenant_id_fkey",
            "collections",
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # 9. Create collection_collaborators table
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'collection_collaborators'"
        )
    )
    if not result.fetchone():
        op.execute("""
            CREATE TABLE collection_collaborators (
                id UUID NOT NULL PRIMARY KEY,
                collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                user_id UUID NOT NULL,
                permission collaboratorpermission NOT NULL DEFAULT 'read',
                invited_by UUID NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT uq_collection_collaborator UNIQUE (collection_id, user_id)
            )
        """)
        op.create_index(
            "ix_collection_collaborators_collection_id",
            "collection_collaborators",
            ["collection_id"],
        )
        op.create_index(
            "ix_collection_collaborators_user_id",
            "collection_collaborators",
            ["user_id"],
        )

    # 10. Create collection_invitations table
    result = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'collection_invitations'"
        )
    )
    if not result.fetchone():
        op.execute("""
            CREATE TABLE collection_invitations (
                id UUID NOT NULL PRIMARY KEY,
                collection_id UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                email VARCHAR(255) NOT NULL,
                permission collaboratorpermission NOT NULL DEFAULT 'read',
                token VARCHAR(64) NOT NULL,
                status invitationstatus NOT NULL DEFAULT 'pending',
                invited_by UUID NOT NULL,
                expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                accepted_at TIMESTAMP WITH TIME ZONE,
                accepted_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT uq_collection_invitation_token UNIQUE (token)
            )
        """)
        op.create_index(
            "ix_collection_invitations_collection_id",
            "collection_invitations",
            ["collection_id"],
        )
        op.create_index(
            "ix_collection_invitations_email",
            "collection_invitations",
            ["email"],
        )
        op.create_index(
            "ix_collection_invitations_token",
            "collection_invitations",
            ["token"],
        )


def downgrade() -> None:
    # Drop collection_invitations table
    op.drop_table("collection_invitations")

    # Drop collection_collaborators table
    op.drop_table("collection_collaborators")

    # Restore tenant_id FK constraint
    op.drop_constraint("collections_tenant_id_fkey", "collections", type_="foreignkey")

    # Set tenant_id from owner_id for organization-owned collections
    op.execute("""
        UPDATE collections
        SET tenant_id = owner_id
        WHERE owner_type = 'organization'
    """)

    # Make tenant_id non-nullable (will fail if there are user-owned collections)
    op.alter_column("collections", "tenant_id", nullable=False)

    # Recreate original FK
    op.create_foreign_key(
        "collections_tenant_id_fkey",
        "collections",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Drop owner constraint and index
    op.drop_constraint("uq_collection_owner_slug", "collections", type_="unique")
    op.drop_index("ix_collections_owner", "collections")

    # Drop ownership columns
    op.drop_column("collections", "owner_id")
    op.drop_column("collections", "owner_type")

    # Drop user_plans table
    op.drop_table("user_plans")

    # Drop enums (only the new ones, not plantype which existed before)
    op.execute("DROP TYPE IF EXISTS collaboratorpermission")
    op.execute("DROP TYPE IF EXISTS ownertype")
    op.execute("DROP TYPE IF EXISTS invitationstatus")

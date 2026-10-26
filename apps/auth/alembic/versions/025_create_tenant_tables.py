# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create tenant and federation tables.

Revision ID: 025
Revises: 018_add_contacts_scopes
Create Date: 2026-01-24

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "025"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE tenantrole AS ENUM ('owner', 'admin', 'member')")
    op.execute(
        "CREATE TYPE identityprovidertype AS ENUM ('oidc', 'saml', 'google', 'github', 'microsoft')"
    )

    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("custom_domain", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
        sa.UniqueConstraint("custom_domain", name=op.f("uq_tenants_custom_domain")),
    )
    op.create_index(op.f("ix_tenants_slug"), "tenants", ["slug"], unique=False)
    op.create_index(op.f("ix_tenants_custom_domain"), "tenants", ["custom_domain"], unique=False)

    # Create tenant_members table
    op.create_table(
        "tenant_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("owner", "admin", "member", name="tenantrole", create_type=False),
            nullable=False,
            server_default="member",
        ),
        sa.Column("invited_by", sa.UUID(), nullable=True),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_members")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_members_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_tenant_members_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["invited_by"],
            ["users.id"],
            name=op.f("fk_tenant_members_invited_by_users"),
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_members_tenant_user"),
    )
    op.create_index(
        op.f("ix_tenant_members_tenant_id"), "tenant_members", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_tenant_members_user_id"), "tenant_members", ["user_id"], unique=False)

    # Create identity_providers table
    op.create_table(
        "identity_providers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "provider_type",
            postgresql.ENUM(
                "oidc",
                "saml",
                "google",
                "github",
                "microsoft",
                name="identityprovidertype",
                create_type=False,
            ),
            nullable=False,
        ),
        # OIDC Configuration
        sa.Column("discovery_url", sa.String(length=2048), nullable=True),
        sa.Column("authorization_endpoint", sa.String(length=2048), nullable=True),
        sa.Column("token_endpoint", sa.String(length=2048), nullable=True),
        sa.Column("userinfo_endpoint", sa.String(length=2048), nullable=True),
        sa.Column("jwks_uri", sa.String(length=2048), nullable=True),
        # Client credentials
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret_encrypted", sa.LargeBinary(), nullable=True),
        # Scopes and attribute mapping
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("attribute_mapping", postgresql.JSONB(), nullable=True),
        sa.Column("allowed_domains", postgresql.ARRAY(sa.String()), nullable=True),
        # Settings
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("auto_provision", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allow_linking", sa.Boolean(), nullable=False, server_default="true"),
        # Display settings
        sa.Column("icon_url", sa.String(length=2048), nullable=True),
        sa.Column("button_text", sa.String(length=100), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        # Timestamps
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_providers")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_identity_providers_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        op.f("ix_identity_providers_tenant_id"), "identity_providers", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_identity_providers_tenant_active",
        "identity_providers",
        ["tenant_id", "is_active"],
        unique=False,
    )

    # Create federated_identities table
    op.create_table(
        "federated_identities",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("identity_provider_id", sa.UUID(), nullable=False),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
        sa.Column("external_email", sa.String(length=255), nullable=True),
        sa.Column("external_username", sa.String(length=255), nullable=True),
        sa.Column("raw_claims", postgresql.JSONB(), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_federated_identities")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_federated_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["identity_provider_id"],
            ["identity_providers.id"],
            name=op.f("fk_federated_identities_identity_provider_id_identity_providers"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "identity_provider_id", "external_subject", name="uq_federated_identities_idp_subject"
        ),
    )
    op.create_index(
        op.f("ix_federated_identities_user_id"), "federated_identities", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_federated_identities_identity_provider_id"),
        "federated_identities",
        ["identity_provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_federated_identities_user_idp",
        "federated_identities",
        ["user_id", "identity_provider_id"],
        unique=False,
    )


def downgrade() -> None:
    # Drop federated_identities table
    op.drop_index("ix_federated_identities_user_idp", table_name="federated_identities")
    op.drop_index(
        op.f("ix_federated_identities_identity_provider_id"), table_name="federated_identities"
    )
    op.drop_index(op.f("ix_federated_identities_user_id"), table_name="federated_identities")
    op.drop_table("federated_identities")

    # Drop identity_providers table
    op.drop_index("ix_identity_providers_tenant_active", table_name="identity_providers")
    op.drop_index(op.f("ix_identity_providers_tenant_id"), table_name="identity_providers")
    op.drop_table("identity_providers")

    # Drop tenant_members table
    op.drop_index(op.f("ix_tenant_members_user_id"), table_name="tenant_members")
    op.drop_index(op.f("ix_tenant_members_tenant_id"), table_name="tenant_members")
    op.drop_table("tenant_members")

    # Drop tenants table
    op.drop_index(op.f("ix_tenants_custom_domain"), table_name="tenants")
    op.drop_index(op.f("ix_tenants_slug"), table_name="tenants")
    op.drop_table("tenants")

    # Drop enum types
    op.execute("DROP TYPE identityprovidertype")
    op.execute("DROP TYPE tenantrole")

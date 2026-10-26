# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create OAuth2 tables.

Revision ID: 008
Revises: 007
Create Date: 2024-12-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create oauth2_clients table
    op.create_table(
        "oauth2_clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("client_secret_hash", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "redirect_uris",
            postgresql.ARRAY(sa.String(length=2048)),
            nullable=False,
        ),
        sa.Column(
            "allowed_scopes",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column(
            "allowed_grant_types",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column(
            "token_endpoint_auth_method",
            sa.String(length=32),
            nullable=False,
            server_default="client_secret_basic",
        ),
        sa.Column("is_confidential", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("require_pkce", sa.Boolean(), nullable=False, default=True),
        sa.Column("require_consent", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth2_clients")),
    )
    op.create_index(
        op.f("ix_oauth2_clients_client_id"),
        "oauth2_clients",
        ["client_id"],
        unique=True,
    )

    # Create authorization_codes table
    op.create_table(
        "authorization_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=2048), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.String(length=64)),
            nullable=False,
        ),
        sa.Column("code_challenge", sa.String(length=128), nullable=True),
        sa.Column("code_challenge_method", sa.String(length=16), nullable=True),
        sa.Column("nonce", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth2_clients.id"],
            name=op.f("fk_authorization_codes_client_id_oauth2_clients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_authorization_codes_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_authorization_codes")),
    )
    op.create_index(
        op.f("ix_authorization_codes_code_hash"),
        "authorization_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_authorization_codes_client_id"),
        "authorization_codes",
        ["client_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_authorization_codes_user_id"),
        "authorization_codes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_authorization_codes_user_id"), table_name="authorization_codes")
    op.drop_index(op.f("ix_authorization_codes_client_id"), table_name="authorization_codes")
    op.drop_index(op.f("ix_authorization_codes_code_hash"), table_name="authorization_codes")
    op.drop_table("authorization_codes")
    op.drop_index(op.f("ix_oauth2_clients_client_id"), table_name="oauth2_clients")
    op.drop_table("oauth2_clients")

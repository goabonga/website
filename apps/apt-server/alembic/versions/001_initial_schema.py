# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create packages, package_acl and index_cache tables."""
    package_visibility = postgresql.ENUM(
        "public",
        "private",
        "shared",
        name="package_visibility",
        create_type=False,
    )
    sa.Enum(
        "public",
        "private",
        "shared",
        name="package_visibility",
    ).create(op.get_bind(), checkfirst=True)

    acl_role = postgresql.ENUM("read", "write", name="package_acl_role", create_type=False)
    sa.Enum("read", "write", name="package_acl_role").create(op.get_bind(), checkfirst=True)

    op.create_table(
        "packages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(255), nullable=False),
        sa.Column("architecture", sa.String(32), nullable=False),
        sa.Column("suite", sa.String(64), nullable=False),
        sa.Column("component", sa.String(64), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column(
            "visibility",
            package_visibility,
            nullable=False,
            server_default="private",
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("md5", sa.String(32), nullable=False),
        sa.Column("sha1", sa.String(40), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "control",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename", name="uq_packages_filename"),
        sa.UniqueConstraint(
            "name",
            "version",
            "architecture",
            "suite",
            "component",
            name="uq_packages_identity",
        ),
    )
    op.create_index("ix_packages_name", "packages", ["name"])
    op.create_index("ix_packages_suite", "packages", ["suite"])
    op.create_index("ix_packages_component", "packages", ["component"])
    op.create_index("ix_packages_owner_id", "packages", ["owner_id"])
    op.create_index("ix_packages_sha256", "packages", ["sha256"])

    op.create_table(
        "package_acl",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grantee_user_id", sa.String(255), nullable=True),
        sa.Column("grantee_group", sa.String(255), nullable=True),
        sa.Column("role", acl_role, nullable=False),
        sa.Column("granted_by", sa.String(255), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["packages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "(grantee_user_id IS NOT NULL) <> (grantee_group IS NOT NULL)",
            name="ck_package_acl_grantee_exclusive",
        ),
    )
    op.create_index("ix_package_acl_package_id", "package_acl", ["package_id"])
    op.create_index("ix_package_acl_grantee_user_id", "package_acl", ["grantee_user_id"])
    op.create_index("ix_package_acl_grantee_group", "package_acl", ["grantee_group"])
    op.create_index(
        "uq_package_acl_user",
        "package_acl",
        ["package_id", "grantee_user_id", "role"],
        unique=True,
        postgresql_where=sa.text("grantee_user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_package_acl_group",
        "package_acl",
        ["package_id", "grantee_group", "role"],
        unique=True,
        postgresql_where=sa.text("grantee_group IS NOT NULL"),
    )

    op.create_table(
        "index_cache",
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )


def downgrade() -> None:
    """Drop the initial schema."""
    op.drop_table("index_cache")

    op.drop_index("uq_package_acl_group", table_name="package_acl")
    op.drop_index("uq_package_acl_user", table_name="package_acl")
    op.drop_index("ix_package_acl_grantee_group", table_name="package_acl")
    op.drop_index("ix_package_acl_grantee_user_id", table_name="package_acl")
    op.drop_index("ix_package_acl_package_id", table_name="package_acl")
    op.drop_table("package_acl")

    op.drop_index("ix_packages_sha256", table_name="packages")
    op.drop_index("ix_packages_owner_id", table_name="packages")
    op.drop_index("ix_packages_component", table_name="packages")
    op.drop_index("ix_packages_suite", table_name="packages")
    op.drop_index("ix_packages_name", table_name="packages")
    op.drop_table("packages")

    sa.Enum(name="package_acl_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="package_visibility").drop(op.get_bind(), checkfirst=True)

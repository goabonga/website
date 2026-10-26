# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add contacts and contact groups tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-02

Creates contacts, contact_groups, and contact_group_members tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    return table_name in inspector.get_table_names()


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists on a table."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    indexes = inspector.get_indexes(table_name)
    return any(idx["name"] == index_name for idx in indexes)


def upgrade() -> None:
    # Create contacts table
    if not table_exists("contacts"):
        op.create_table(
            "contacts",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("client_id", sa.String(255), nullable=False),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("first_name", sa.String(100), nullable=True),
            sa.Column("last_name", sa.String(100), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("source", sa.String(100), nullable=True),
            sa.Column(
                "custom_fields",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default="{}",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id", "email", name="uq_contacts_client_email"),
        )

    # Create indexes for contacts
    if table_exists("contacts"):
        if not index_exists("contacts", "ix_contacts_client_id"):
            op.create_index("ix_contacts_client_id", "contacts", ["client_id"])
        if not index_exists("contacts", "ix_contacts_email"):
            op.create_index("ix_contacts_email", "contacts", ["email"])
        if not index_exists("contacts", "ix_contacts_status"):
            op.create_index("ix_contacts_status", "contacts", ["status"])

    # Create contact_groups table
    if not table_exists("contact_groups"):
        op.create_table(
            "contact_groups",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("client_id", sa.String(255), nullable=False),
            sa.Column("slug", sa.String(100), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column(
                "filter_criteria",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id", "slug", name="uq_contact_groups_client_slug"),
        )

    # Create indexes for contact_groups
    if table_exists("contact_groups"):
        if not index_exists("contact_groups", "ix_contact_groups_client_id"):
            op.create_index("ix_contact_groups_client_id", "contact_groups", ["client_id"])
        if not index_exists("contact_groups", "ix_contact_groups_slug"):
            op.create_index("ix_contact_groups_slug", "contact_groups", ["slug"])

    # Create contact_group_members table
    if not table_exists("contact_group_members"):
        op.create_table(
            "contact_group_members",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("group_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["group_id"], ["contact_groups.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("contact_id", "group_id", name="uq_contact_group_member"),
        )

    # Create indexes for contact_group_members
    if table_exists("contact_group_members"):
        if not index_exists("contact_group_members", "ix_contact_group_members_contact_id"):
            op.create_index(
                "ix_contact_group_members_contact_id",
                "contact_group_members",
                ["contact_id"],
            )
        if not index_exists("contact_group_members", "ix_contact_group_members_group_id"):
            op.create_index(
                "ix_contact_group_members_group_id",
                "contact_group_members",
                ["group_id"],
            )


def downgrade() -> None:
    # Drop contact_group_members indexes and table
    op.drop_index("ix_contact_group_members_group_id", table_name="contact_group_members")
    op.drop_index("ix_contact_group_members_contact_id", table_name="contact_group_members")
    op.drop_table("contact_group_members")

    # Drop contact_groups indexes and table
    op.drop_index("ix_contact_groups_slug", table_name="contact_groups")
    op.drop_index("ix_contact_groups_client_id", table_name="contact_groups")
    op.drop_table("contact_groups")

    # Drop contacts indexes and table
    op.drop_index("ix_contacts_status", table_name="contacts")
    op.drop_index("ix_contacts_email", table_name="contacts")
    op.drop_index("ix_contacts_client_id", table_name="contacts")
    op.drop_table("contacts")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create contacts, contact_groups, and contact_group_members tables.

Revision ID: 007_create_contacts_tables
Revises: 006_create_email_templates
Create Date: 2026-01-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_create_contacts_tables"
down_revision: str | None = "006_create_email_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create contacts, contact_groups, and contact_group_members tables."""
    # Create contacts table
    op.create_table(
        "contacts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active", index=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column(
            "custom_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
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
    )

    # Create contact_groups table
    op.create_table(
        "contact_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("slug", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "filter_criteria",
            postgresql.JSONB(),
            nullable=True,
        ),
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
    )

    # Create contact_group_members association table
    op.create_table(
        "contact_group_members",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "contact_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("contact_groups.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("contact_id", "group_id", name="uq_contact_group_member"),
    )


def downgrade() -> None:
    """Drop contacts, contact_groups, and contact_group_members tables."""
    op.drop_table("contact_group_members")
    op.drop_table("contact_groups")
    op.drop_table("contacts")

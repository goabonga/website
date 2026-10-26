# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the authorized clients registry.

Revision ID: 006
Revises: 005
Create Date: 2026-10-26

Creates the authorized_clients table. It also brings a database created before
the data was scoped to clients up to date: templates, contacts, contact groups
and campaigns get their required ``client_id`` (existing rows are attributed to
``LEGACY_CLIENT_ID``), and the slug / email uniqueness becomes per client.
Databases created by revisions 002 to 004 of this version already have all of
that, so every step checks before it changes anything.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from mailler.config import settings
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: str | None = "005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> (unique column, constraint name, index that used to be unique on its own)
CLIENT_SCOPED_TABLES: dict[str, tuple[str | None, str | None, str | None]] = {
    "email_templates": ("slug", "uq_email_templates_client_slug", "ix_email_templates_slug"),
    "contacts": ("email", "uq_contacts_client_email", "ix_contacts_email"),
    "contact_groups": ("slug", "uq_contact_groups_client_slug", "ix_contact_groups_slug"),
    "email_campaigns": (None, None, None),
}

JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    return table_name in _inspector().get_table_names()


def column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table."""
    return any(c["name"] == column_name for c in _inspector().get_columns(table_name))


def find_index(table_name: str, index_name: str) -> dict | None:
    """Return the description of an index of a table, or None."""
    for index in _inspector().get_indexes(table_name):
        if index["name"] == index_name:
            return index
    return None


def constraint_exists(table_name: str, constraint_name: str) -> bool:
    """Check if a unique constraint (or unique index) with that name exists on a table."""
    inspector = _inspector()
    if any(c["name"] == constraint_name for c in inspector.get_unique_constraints(table_name)):
        return True
    index = find_index(table_name, constraint_name)
    return bool(index and index.get("unique"))


def scope_table_to_clients(
    table: str, unique_column: str | None, constraint: str | None, old_index: str | None
) -> None:
    """Make an existing table client scoped (idempotent)."""
    if not table_exists(table):
        return
    bind = op.get_bind()

    if not column_exists(table, "client_id"):
        op.add_column(table, sa.Column("client_id", sa.String(255), nullable=True))

    if settings.legacy_client_id:
        bind.execute(
            sa.text(f"UPDATE {table} SET client_id = :client WHERE client_id IS NULL"),  # noqa: S608
            {"client": settings.legacy_client_id},
        )
    orphans = bind.execute(
        sa.text(f"SELECT count(*) FROM {table} WHERE client_id IS NULL")  # noqa: S608
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} row(s) of {table} belong to no client: set LEGACY_CLIENT_ID to the "
            "client that owns the data that existed before client scoping, then run the "
            "migration again"
        )

    with op.batch_alter_table(table) as batch:
        batch.alter_column("client_id", existing_type=sa.String(255), nullable=False)

    if not find_index(table, f"ix_{table}_client_id"):
        op.create_index(f"ix_{table}_client_id", table, ["client_id"])

    if old_index:
        index = find_index(table, old_index)
        if index and index.get("unique"):
            op.drop_index(old_index, table_name=table)
            op.create_index(old_index, table, index["column_names"])

    if unique_column and constraint and not constraint_exists(table, constraint):
        with op.batch_alter_table(table) as batch:
            batch.create_unique_constraint(constraint, ["client_id", unique_column])


def upgrade() -> None:
    if not table_exists("authorized_clients"):
        op.create_table(
            "authorized_clients",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("client_id", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("from_email", sa.String(255), nullable=True),
            sa.Column("from_name", sa.String(255), nullable=True),
            sa.Column("reply_to", sa.String(255), nullable=True),
            sa.Column("allowed_senders", JSON_TYPE, nullable=False, server_default="[]"),
            sa.Column("allowed_providers", JSON_TYPE, nullable=False, server_default="[]"),
            sa.Column("default_provider", sa.String(50), nullable=True),
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
        )
        op.create_index(
            "ix_authorized_clients_client_id", "authorized_clients", ["client_id"], unique=True
        )

    for table, (unique_column, constraint, old_index) in CLIENT_SCOPED_TABLES.items():
        scope_table_to_clients(table, unique_column, constraint, old_index)

    # Emails sent before client scoping have no owner either
    if settings.legacy_client_id and table_exists("emails"):
        op.get_bind().execute(
            sa.text("UPDATE emails SET client_id = :client WHERE client_id IS NULL"),
            {"client": settings.legacy_client_id},
        )


def downgrade() -> None:
    # Only the registry is dropped: the client scoping of the data is not undone.
    op.drop_index("ix_authorized_clients_client_id", table_name="authorized_clients")
    op.drop_table("authorized_clients")

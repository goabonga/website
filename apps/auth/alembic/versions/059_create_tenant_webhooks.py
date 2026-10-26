# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Create tenant webhooks and delivery tables.

Revision ID: 059
Revises: 057
Create Date: 2026-04-19

Adds outbound webhook support for tenants:
- ``tenant_webhooks``: subscription rows (name, url, subscribed events, secret,
  extra headers, active flag, lightweight last-delivery stats).
- ``webhook_deliveries``: per-event delivery attempt chains with request and
  response snapshots for debugging and replay.

Also appends ``webhooks:*`` to existing system tenant ``admin`` roles so
admins inherit the new capability without a manual role edit.

Idempotent on the ``webhookdeliverystatus`` enum creation so a re-run after
a partial failure succeeds without a manual ``DROP TYPE``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "059"
down_revision: str | None = "057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create the enum type up-front, idempotently. PostgreSQL does not
    # support ``CREATE TYPE ... IF NOT EXISTS`` so we use a DO block that
    # swallows the duplicate_object exception. This is required because the
    # initial version of this migration double-created the type (once here
    # and once implicitly via ``sa.Enum`` inside ``op.create_table``),
    # leaving partially-migrated environments with the enum already present.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE webhookdeliverystatus AS ENUM
                ('pending', 'success', 'failed', 'retrying');
        EXCEPTION WHEN duplicate_object THEN
            NULL;
        END
        $$;
        """
    )

    # tenant_webhooks
    op.create_table(
        "tenant_webhooks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column(
            "events",
            postgresql.ARRAY(sa.String(64)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_webhooks")),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_tenant_webhooks_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_tenant_webhooks_tenant_id", "tenant_webhooks", ["tenant_id"])
    op.create_index(
        "ix_tenant_webhooks_events",
        "tenant_webhooks",
        ["events"],
        postgresql_using="gin",
    )

    # webhook_deliveries: use postgresql.ENUM with create_type=False so that
    # the column references the enum we created above without SQLAlchemy
    # trying to CREATE TYPE a second time during op.create_table.
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("webhook_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_url", sa.String(2048), nullable=False),
        sa.Column(
            "request_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "request_body",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "success",
                "failed",
                "retrying",
                name="webhookdeliverystatus",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column(
            "response_headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webhook_deliveries")),
        sa.ForeignKeyConstraint(
            ["webhook_id"],
            ["tenant_webhooks.id"],
            name=op.f("fk_webhook_deliveries_webhook_id_tenant_webhooks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_webhook_deliveries_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name=op.f("uq_webhook_deliveries_idempotency_key"),
        ),
    )
    op.create_index("ix_webhook_deliveries_event", "webhook_deliveries", ["event"])
    op.create_index(
        "ix_webhook_deliveries_webhook_created",
        "webhook_deliveries",
        ["webhook_id", "created_at"],
    )
    op.create_index(
        "ix_webhook_deliveries_tenant_created",
        "webhook_deliveries",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_webhook_deliveries_retry",
        "webhook_deliveries",
        ["status", "next_retry_at"],
    )

    # Grant webhooks:* to existing system admin tenant roles so the capability
    # is available out of the box without re-editing roles.
    op.execute(
        sa.text(
            """
            UPDATE tenant_roles
            SET scopes = array_append(scopes, 'webhooks:*')
            WHERE is_system = true
              AND name = 'admin'
              AND NOT ('webhooks:*' = ANY(scopes))
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE tenant_roles
            SET scopes = array_remove(scopes, 'webhooks:*')
            WHERE is_system = true AND name = 'admin'
            """
        )
    )

    op.drop_index("ix_webhook_deliveries_retry", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_tenant_created", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_webhook_created", table_name="webhook_deliveries")
    op.drop_index("ix_webhook_deliveries_event", table_name="webhook_deliveries")
    op.drop_table("webhook_deliveries")

    op.execute("DROP TYPE IF EXISTS webhookdeliverystatus")

    op.drop_index("ix_tenant_webhooks_events", table_name="tenant_webhooks")
    op.drop_index("ix_tenant_webhooks_tenant_id", table_name="tenant_webhooks")
    op.drop_table("tenant_webhooks")

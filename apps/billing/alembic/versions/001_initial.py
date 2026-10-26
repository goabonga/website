# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Initial migration - create all billing tables.

Revision ID: 001
Revises:
Create Date: 2025-01-28

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create billing_type enum
    billing_type_enum = postgresql.ENUM(
        "one_time", "recurring", name="billingtype", create_type=False
    )
    billing_type_enum.create(op.get_bind(), checkfirst=True)

    # Create usage_type enum
    usage_type_enum = postgresql.ENUM("licensed", "metered", name="usagetype", create_type=False)
    usage_type_enum.create(op.get_bind(), checkfirst=True)

    # Create subscription_status enum
    subscription_status_enum = postgresql.ENUM(
        "active",
        "past_due",
        "unpaid",
        "canceled",
        "incomplete",
        "incomplete_expired",
        "trialing",
        "paused",
        name="subscriptionstatus",
        create_type=False,
    )
    subscription_status_enum.create(op.get_bind(), checkfirst=True)

    # Create usage_event_status enum
    usage_event_status_enum = postgresql.ENUM(
        "pending", "reported", "failed", name="usageeventstatus", create_type=False
    )
    usage_event_status_enum.create(op.get_bind(), checkfirst=True)

    # Create saas_apps table
    op.create_table(
        "saas_apps",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("webhook_url", sa.String(500), nullable=True),
        sa.Column("webhook_secret", sa.String(255), nullable=True),
        sa.Column("branding", postgresql.JSONB, nullable=True),
        sa.Column("rate_limit_requests", sa.Integer, default=100),
        sa.Column("rate_limit_window", sa.Integer, default=60),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Create billing_products table
    op.create_table(
        "billing_products",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "saas_app_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("saas_apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stripe_product_id", sa.String(100), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("saas_app_id", "stripe_product_id", name="uq_product_saas_stripe"),
    )
    op.create_index("ix_products_saas_app", "billing_products", ["saas_app_id"])

    # Create billing_prices table
    op.create_table(
        "billing_prices",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("billing_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stripe_price_id", sa.String(100), nullable=False, index=True),
        sa.Column("nickname", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(3)),
        sa.Column("unit_amount", sa.Integer, nullable=True),
        sa.Column(
            "billing_type",
            billing_type_enum,
            default="recurring",
        ),
        sa.Column("recurring_interval", sa.String(20), nullable=True),
        sa.Column("recurring_interval_count", sa.Integer, default=1),
        sa.Column("usage_type", usage_type_enum, default="licensed"),
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("product_id", "stripe_price_id", name="uq_price_product_stripe"),
    )
    op.create_index("ix_prices_product", "billing_prices", ["product_id"])

    # Create customers table
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "saas_app_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("saas_apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("stripe_customer_id", sa.String(100), nullable=False, index=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("saas_app_id", "external_id", name="uq_customer_saas_external"),
        sa.UniqueConstraint("saas_app_id", "stripe_customer_id", name="uq_customer_saas_stripe"),
    )
    op.create_index("ix_customers_saas_app", "customers", ["saas_app_id"])
    op.create_index("ix_customers_email", "customers", ["email"])

    # Create subscriptions table
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "price_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("billing_prices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=False, index=True),
        sa.Column("stripe_subscription_item_id", sa.String(100), nullable=True),
        sa.Column("status", subscription_status_enum, default="active"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean, default=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "customer_id", "stripe_subscription_id", name="uq_subscription_customer_stripe"
        ),
    )
    op.create_index("ix_subscriptions_customer", "subscriptions", ["customer_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])

    # Create usage_events table
    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("status", usage_event_status_enum, default="pending"),
        sa.Column("stripe_usage_record_id", sa.String(100), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("action", sa.String(100), nullable=True),
        sa.Column("extra_data", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_usage_events_subscription", "usage_events", ["subscription_id"])
    op.create_index("ix_usage_events_status", "usage_events", ["status"])
    op.create_index("ix_usage_events_timestamp", "usage_events", ["timestamp"])
    # Partial index for pending events
    op.create_index(
        "ix_usage_events_pending",
        "usage_events",
        ["status", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("usage_events")
    op.drop_table("subscriptions")
    op.drop_table("customers")
    op.drop_table("billing_prices")
    op.drop_table("billing_products")
    op.drop_table("saas_apps")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS usageeventstatus")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS usagetype")
    op.execute("DROP TYPE IF EXISTS billingtype")

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Scope plan slugs and usage idempotency keys to a SaaS application.

* ``billing_products.slug`` is a real column, unique per SaaS application.
  Existing rows take the ``slug`` stored in ``extra_data`` (or a slug built
  from the product name); duplicates inside one SaaS application get a
  numeric suffix so that the unique constraint can be created.
* ``usage_events.saas_app_id`` records the owner of each event and the
  idempotency key becomes unique per SaaS application instead of globally.
* ``saas_apps.checkout_url_allowlist`` lists the URL prefixes accepted as
  checkout success and cancel targets of the SaaS application.

Revision ID: 005
Revises: 004
Create Date: 2026-03-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Slug of a product: lower case, runs of other characters collapsed to "-".
_SLUG_BACKFILL = """
WITH base AS (
    SELECT
        id,
        saas_app_id,
        COALESCE(
            NULLIF(trim(both '-' from regexp_replace(
                lower(COALESCE(extra_data->>'slug', name)), '[^a-z0-9]+', '-', 'g'
            )), ''),
            'p-' || substr(id::text, 1, 8)
        ) AS slug
    FROM billing_products
),
ranked AS (
    SELECT
        id,
        slug,
        row_number() OVER (PARTITION BY saas_app_id, slug ORDER BY id) AS rn
    FROM base
)
UPDATE billing_products AS p
SET slug = CASE WHEN r.rn = 1 THEN r.slug ELSE r.slug || '-' || r.rn END
FROM ranked AS r
WHERE p.id = r.id
"""


def upgrade() -> None:
    # Plan slug as a column, unique per SaaS application.
    op.add_column("billing_products", sa.Column("slug", sa.String(100), nullable=True))
    op.execute(_SLUG_BACKFILL)
    op.alter_column("billing_products", "slug", nullable=False)
    op.create_unique_constraint("uq_product_saas_slug", "billing_products", ["saas_app_id", "slug"])

    # Usage events know their SaaS application; idempotency is per SaaS.
    op.add_column(
        "usage_events",
        sa.Column("saas_app_id", postgresql.UUID(as_uuid=False), nullable=True),
    )
    op.execute(
        """
        UPDATE usage_events AS u
        SET saas_app_id = c.saas_app_id
        FROM subscriptions AS s
        JOIN customers AS c ON c.id = s.customer_id
        WHERE s.id = u.subscription_id
        """
    )
    op.alter_column("usage_events", "saas_app_id", nullable=False)
    op.create_foreign_key(
        "fk_usage_events_saas_app",
        "usage_events",
        "saas_apps",
        ["saas_app_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_usage_events_saas_app", "usage_events", ["saas_app_id"])
    op.drop_constraint("usage_events_idempotency_key_key", "usage_events", type_="unique")
    op.create_unique_constraint(
        "uq_usage_saas_idempotency", "usage_events", ["saas_app_id", "idempotency_key"]
    )

    # Redirect targets accepted by the checkout of each SaaS application.
    op.add_column(
        "saas_apps",
        sa.Column("checkout_url_allowlist", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("saas_apps", "checkout_url_allowlist")

    op.drop_constraint("uq_usage_saas_idempotency", "usage_events", type_="unique")
    op.create_unique_constraint(
        "usage_events_idempotency_key_key", "usage_events", ["idempotency_key"]
    )
    op.drop_index("ix_usage_events_saas_app", table_name="usage_events")
    op.drop_constraint("fk_usage_events_saas_app", "usage_events", type_="foreignkey")
    op.drop_column("usage_events", "saas_app_id")

    op.drop_constraint("uq_product_saas_slug", "billing_products", type_="unique")
    op.drop_column("billing_products", "slug")

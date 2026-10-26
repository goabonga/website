# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Track the custom domain in the custom-domain service.

The DNS verification, the certificate and the web server configuration are done by the
custom-domain service, which identifies a registered domain by an id. The organization
keeps that id (to ask for its status, restart the verification or delete it) and the
CNAME target the service told the customer to use.

Domains that were already configured by the application have no id yet: the
reconciliation task registers them in the service.

Revision ID: 009_custom_domain_service
Revises: 008_add_custom_domain_fields
Create Date: 2026-02-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "009_custom_domain_service"
down_revision: str | None = "008_add_custom_domain_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("custom_domain_service_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "tenants",
        sa.Column("custom_domain_cname_target", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_tenants_custom_domain_service_id",
        "tenants",
        ["custom_domain_service_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tenants_custom_domain_service_id", table_name="tenants")
    op.drop_column("tenants", "custom_domain_cname_target")
    op.drop_column("tenants", "custom_domain_service_id")

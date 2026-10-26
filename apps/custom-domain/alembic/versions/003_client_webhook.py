# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add the webhook callback to authorized clients.

Revision ID: 003_client_webhook
Revises: 002_template_owner
Create Date: 2026-01-02 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_client_webhook"
down_revision: str | None = "002_template_owner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "authorized_clients",
        sa.Column(
            "webhook_url",
            sa.String(length=1000),
            nullable=True,
            comment="URL that receives signed status notifications",
        ),
    )
    op.add_column(
        "authorized_clients",
        sa.Column(
            "webhook_secret",
            sa.String(length=255),
            nullable=True,
            comment="HMAC secret shared with the client",
        ),
    )


def downgrade() -> None:
    op.drop_column("authorized_clients", "webhook_secret")
    op.drop_column("authorized_clients", "webhook_url")

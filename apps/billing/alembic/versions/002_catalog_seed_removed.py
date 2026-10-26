# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Former catalog seed, now an empty revision.

This revision used to insert a fixed tenant with its plans. Tenants, plans
and their Stripe identifiers are deployment data: they are created through
the admin API or the ``billing-admin`` command, never by a migration. The
revision is kept, empty, so that the history of existing databases stays
continuous.

Revision ID: 002
Revises: 001
Create Date: 2025-01-31

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to do: no data is seeded."""


def downgrade() -> None:
    """Nothing to do: no data was seeded."""

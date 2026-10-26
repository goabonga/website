# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Drop current_conversation_id from anonymous_sessions.

Revision ID: 002_drop_current_conversation_id
Revises: 001_initial_schema
Create Date: 2026-01-02
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "002_drop_current_conversation_id"
down_revision: str | None = "001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: column was already removed from 001_initial_schema
    pass


def downgrade() -> None:
    # No-op: column was never created in 001_initial_schema
    pass

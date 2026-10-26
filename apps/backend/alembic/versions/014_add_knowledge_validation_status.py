# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add validation status and details to knowledge entries.

Revision ID: 014_add_knowledge_status
Revises: 013_drop_email_tables
Create Date: 2026-02-14

Adds status and validation_details columns to the knowledge_base table
to support the asynchronous knowledge validation pipeline.

- status: tracks validation state (pending, validating, accepted, rejected, needs_review)
- validation_details: stores per-step validation results as JSONB

Existing entries default to 'accepted' for backward compatibility.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "014_add_knowledge_status"
down_revision: str | None = "013_drop_email_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add validation columns to knowledge_base."""
    op.add_column(
        "knowledge_base",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="accepted",
        ),
    )
    op.add_column(
        "knowledge_base",
        sa.Column(
            "validation_details",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_base_status",
        "knowledge_base",
        ["status"],
    )


def downgrade() -> None:
    """Remove validation columns from knowledge_base."""
    op.drop_index("ix_knowledge_base_status", table_name="knowledge_base")
    op.drop_column("knowledge_base", "validation_details")
    op.drop_column("knowledge_base", "status")

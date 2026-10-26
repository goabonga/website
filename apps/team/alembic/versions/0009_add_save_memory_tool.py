# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""0009 add the save_memory tool to the agents

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-26
"""

from alembic import op
from sqlalchemy import text

# revision identifiers
revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add save_memory to all agents that don't have it yet
    op.execute(
        text(
            """
            UPDATE agents
            SET config = jsonb_set(
                config,
                '{tools}',
                (config->'tools') || '"save_memory"'::jsonb
            )
            WHERE config->'tools' IS NOT NULL
              AND NOT (config->'tools' @> '"save_memory"'::jsonb)
            """
        )
    )


def downgrade() -> None:
    # Remove save_memory from agents tools
    op.execute(
        text(
            """
            UPDATE agents
            SET config = jsonb_set(
                config,
                '{tools}',
                (config->'tools') - 'save_memory'
            )
            WHERE config->'tools' IS NOT NULL
              AND config->'tools' @> '"save_memory"'::jsonb
            """
        )
    )

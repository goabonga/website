# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""0011 add update_memory and delete_memory tools to agents.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-26
"""

from alembic import op
from sqlalchemy import text

# revision identifiers
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

# Agents with save_memory get update_memory and delete_memory
_TOOL_PAIRS = [
    ("save_memory", "update_memory"),
    ("save_memory", "delete_memory"),
]


def upgrade() -> None:
    for existing_tool, new_tool in _TOOL_PAIRS:
        op.execute(
            text(
                """
                UPDATE agents
                SET config = jsonb_set(
                    config,
                    '{tools}',
                    (config->'tools') || CAST(:new_tool AS jsonb)
                )
                WHERE config->'tools' IS NOT NULL
                  AND config->'tools' @> CAST(:existing_tool AS jsonb)
                  AND NOT (config->'tools' @> CAST(:new_tool AS jsonb))
                """
            ).bindparams(
                existing_tool=f'"{existing_tool}"',
                new_tool=f'"{new_tool}"',
            )
        )


def downgrade() -> None:
    for _, new_tool in _TOOL_PAIRS:
        op.execute(
            text(
                """
                UPDATE agents
                SET config = jsonb_set(
                    config,
                    '{tools}',
                    (config->'tools') - :tool_name
                )
                WHERE config->'tools' IS NOT NULL
                  AND config->'tools' @> CAST(:new_tool AS jsonb)
                """
            ).bindparams(
                tool_name=new_tool,
                new_tool=f'"{new_tool}"',
            )
        )

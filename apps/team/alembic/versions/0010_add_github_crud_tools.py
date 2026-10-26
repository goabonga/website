# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""0010 add github CRUD tools + git_create_branch + git_diff to agents.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-26
"""

from alembic import op
from sqlalchemy import text

# revision identifiers
revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

# New tools to add to agents that already have the corresponding create tool
_TOOL_PAIRS = [
    ("github_create_issue", "github_get_issue"),
    ("github_create_issue", "github_update_issue"),
    ("github_create_pr", "github_get_pr"),
    ("github_create_pr", "github_update_pr"),
    ("github_comment", "github_list_comments"),
    ("github_create_pr", "github_list_review_comments"),
    ("github_comment", "github_update_comment"),
    ("github_comment", "github_delete_comment"),
    # git branch/diff tools for agents that can clone
    ("git_clone", "git_create_branch"),
    ("git_clone", "git_diff"),
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

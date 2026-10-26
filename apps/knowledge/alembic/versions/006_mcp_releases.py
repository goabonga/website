# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Add MCP releases tables for executable distribution.

Revision ID: 006_mcp_releases
Revises: 005_member_display_info
Create Date: 2026-02-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "006_mcp_releases"
down_revision: str | None = "005_member_display_info"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Create releasestatus enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'releasestatus'"))
    if not result.fetchone():
        op.execute("CREATE TYPE releasestatus AS ENUM ('draft', 'published', 'deprecated')")

    # Create platform enum
    result = conn.execute(sa.text("SELECT 1 FROM pg_type WHERE typname = 'platform'"))
    if not result.fetchone():
        op.execute(
            "CREATE TYPE platform AS ENUM ('linux-x86_64', 'linux-arm64', 'macos-x86_64', 'macos-arm64', 'windows-x86_64')"
        )

    # Create mcp_releases table
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'mcp_releases'")
    )
    if not result.fetchone():
        op.execute(
            """
            CREATE TABLE mcp_releases (
                id UUID NOT NULL PRIMARY KEY,
                version VARCHAR(50) NOT NULL,
                github_release_id BIGINT NOT NULL,
                release_notes TEXT,
                status releasestatus NOT NULL DEFAULT 'published',
                published_at TIMESTAMP WITH TIME ZONE,
                metadata JSONB,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT uq_mcp_releases_version UNIQUE (version),
                CONSTRAINT uq_mcp_releases_github_release_id UNIQUE (github_release_id)
            )
        """
        )
        op.create_index(
            "ix_mcp_releases_version",
            "mcp_releases",
            ["version"],
        )
        op.create_index(
            "ix_mcp_releases_status",
            "mcp_releases",
            ["status"],
        )
        op.create_index(
            "ix_mcp_releases_status_published_at",
            "mcp_releases",
            ["status", "published_at"],
        )

    # Create mcp_release_assets table
    result = conn.execute(
        sa.text("SELECT 1 FROM information_schema.tables WHERE table_name = 'mcp_release_assets'")
    )
    if not result.fetchone():
        op.execute(
            """
            CREATE TABLE mcp_release_assets (
                id UUID NOT NULL PRIMARY KEY,
                release_id UUID NOT NULL REFERENCES mcp_releases(id) ON DELETE CASCADE,
                platform platform NOT NULL,
                filename VARCHAR(255) NOT NULL,
                download_url VARCHAR(1024) NOT NULL,
                file_size BIGINT,
                sha256_checksum VARCHAR(64),
                download_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
            )
        """
        )
        op.create_index(
            "ix_mcp_release_assets_release_id",
            "mcp_release_assets",
            ["release_id"],
        )
        op.create_index(
            "ix_mcp_release_assets_release_platform",
            "mcp_release_assets",
            ["release_id", "platform"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_table("mcp_release_assets")
    op.drop_table("mcp_releases")
    op.execute("DROP TYPE IF EXISTS platform")
    op.execute("DROP TYPE IF EXISTS releasestatus")

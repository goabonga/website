# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Initial migration - create all tables.

Revision ID: 001_initial
Revises:
Create Date: 2025-01-23

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create tenants table
    op.create_table(
        "tenants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column(
            "plan",
            sa.Enum("FREE", "STARTER", "PRO", "ENTERPRISE", name="plantype"),
            nullable=False,
        ),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_tenants_slug", "tenants", ["slug"])

    # Create collections table
    op.create_table(
        "collections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column(
            "embedding_model",
            sa.String(100),
            nullable=False,
            default="text-embedding-3-small",
        ),
        sa.Column("dimension", sa.Integer(), nullable=False, default=1536),
        sa.Column("metadata_schema", sa.JSON(), nullable=True),
        sa.Column("document_count", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_collection_tenant_slug"),
    )
    op.create_index("ix_collections_tenant_id", "collections", ["tenant_id"])
    op.create_index("ix_collections_slug", "collections", ["slug"])

    # Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("collection_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, default={}),
        sa.Column("source_type", sa.String(50), nullable=True),
        sa.Column("source_ref", sa.String(500), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_documents_collection_id", "documents", ["collection_id"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])

    # Create HNSW index for vector similarity search
    op.execute(
        """
        CREATE INDEX ix_documents_embedding ON documents
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )

    # Create usage_records table
    op.create_table(
        "usage_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("metric", sa.String(50), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False, default=0),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_usage_records_tenant_id", "usage_records", ["tenant_id"])
    op.create_index(
        "ix_usage_tenant_metric_period",
        "usage_records",
        ["tenant_id", "metric", "period"],
    )


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("documents")
    op.drop_table("collections")
    op.drop_table("tenants")
    op.execute("DROP TYPE IF EXISTS plantype")
    op.execute("DROP EXTENSION IF EXISTS vector")

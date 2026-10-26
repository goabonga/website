# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Unit tests for the Alembic migration chain and the declared metadata."""

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from knowledge.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

EXPECTED_REVISIONS = [
    "001_initial",
    "002_multi_tenant_web",
    "003_github_ownership",
    "004_workspace_deletion_requests",
    "005_member_display_info",
    "006_mcp_releases",
    "007_workspace_deletion_scheduled",
    "008_add_custom_domain_fields",
    "009_custom_domain_service",
]

EXPECTED_TABLES = {
    "tenants",
    "tenant_members",
    "invitations",
    "collections",
    "documents",
    "usage_records",
    "user_plans",
    "collection_collaborators",
    "collection_invitations",
    "workspace_deletion_requests",
    "mcp_releases",
    "mcp_release_assets",
}


@pytest.fixture
def script() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


class TestMigrationChain:
    """The migration history is a single linear chain."""

    def test_single_head(self, script):
        assert script.get_heads() == ["009_custom_domain_service"]

    def test_chain_is_linear_and_ordered(self, script):
        revisions = [rev.revision for rev in script.walk_revisions()]
        assert list(reversed(revisions)) == EXPECTED_REVISIONS

    def test_single_base(self, script):
        assert script.get_bases() == ["001_initial"]

    def test_every_revision_has_a_downgrade(self, script):
        for rev in script.walk_revisions():
            assert hasattr(rev.module, "downgrade"), rev.revision


class TestMetadata:
    """The declarative metadata matches the tables created by the migrations."""

    def test_tables_registered(self):
        assert set(Base.metadata.tables) == EXPECTED_TABLES

    def test_documents_have_vector_embedding_index(self):
        documents = Base.metadata.tables["documents"]
        index_names = {index.name for index in documents.indexes}
        assert "ix_documents_embedding" in index_names

    def test_collections_have_polymorphic_owner_columns(self):
        collections = Base.metadata.tables["collections"]
        assert {"owner_type", "owner_id", "tenant_id"} <= set(collections.columns.keys())

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


class TestCustomDomainServiceRevision:
    """Revision 009 adds the columns that link a workspace to the custom-domain service."""

    def _run(self, direction):
        import importlib.util

        import sqlalchemy as sa
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        path = ALEMBIC_INI.parent / "alembic" / "versions" / "009_custom_domain_service.py"
        spec = importlib.util.spec_from_file_location("revision_009", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        engine = sa.create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(sa.text("CREATE TABLE tenants (id INTEGER PRIMARY KEY)"))
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
                if direction == "down":
                    module.downgrade()
            inspector = sa.inspect(connection)
            return (
                {column["name"] for column in inspector.get_columns("tenants")},
                {index["name"]: index["unique"] for index in inspector.get_indexes("tenants")},
            )

    def test_upgrade_adds_the_columns_and_a_unique_index(self):
        columns, indexes = self._run("up")
        assert {"custom_domain_service_id", "custom_domain_cname_target"} <= columns
        assert bool(indexes["ix_tenants_custom_domain_service_id"]) is True

    def test_downgrade_removes_them(self):
        columns, indexes = self._run("down")
        assert columns == {"id"}
        assert indexes == {}

    def test_the_model_declares_the_same_columns(self):
        table = Base.metadata.tables["tenants"]
        assert table.c.custom_domain_service_id.unique is True
        assert table.c.custom_domain_service_id.nullable is True
        assert table.c.custom_domain_cname_target.nullable is True

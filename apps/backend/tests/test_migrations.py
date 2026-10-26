# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic migration chain."""

import io
from pathlib import Path

import backend.models  # noqa: F401
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from backend.database import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
HEAD = "014_add_knowledge_status"


@pytest.fixture
def alembic_config(monkeypatch) -> Config:
    """Return the Alembic configuration pointing at a throw-away database URL."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/migrations")
    return Config(str(ALEMBIC_INI))


@pytest.fixture
def scripts(alembic_config) -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config)


@pytest.fixture
def upgrade_sql(alembic_config) -> str:
    """Render the whole upgrade to SQL in offline mode (no database needed)."""
    buffer = io.StringIO()
    alembic_config.output_buffer = buffer
    command.upgrade(alembic_config, "head", sql=True)
    return buffer.getvalue()


class TestRevisionChain:
    """The revision history must stay a single linear chain."""

    def test_single_head(self, scripts):
        assert scripts.get_heads() == [HEAD]

    def test_chain_is_linear_and_numbered(self, scripts):
        revisions = list(scripts.walk_revisions())
        assert len(revisions) == 14
        for revision in revisions:
            assert isinstance(revision.down_revision, str | type(None))
        numbers = [int(r.revision[:3]) for r in reversed(revisions)]
        assert numbers == list(range(1, 15))

    def test_single_base(self, scripts):
        assert scripts.get_bases() == ["001_initial_schema"]


class TestOfflineUpgrade:
    """The SQL generated for a fresh database."""

    def test_creates_every_model_table(self, upgrade_sql):
        for table in Base.metadata.tables:
            assert f"CREATE TABLE {table} " in upgrade_sql, table

    def test_creates_prompt_and_namespace_tables(self, upgrade_sql):
        assert "CREATE TABLE system_prompts " in upgrade_sql
        assert "CREATE TABLE system_prompt_versions " in upgrade_sql
        assert "CREATE TABLE knowledge_namespaces " in upgrade_sql

    def test_drops_the_email_tables_moved_to_mailler(self, upgrade_sql):
        assert "DROP TABLE email_templates" in upgrade_sql
        assert "DROP TABLE contacts" in upgrade_sql

    def test_records_the_head_revision(self, upgrade_sql):
        assert f"UPDATE alembic_version SET version_num='{HEAD}'" in upgrade_sql


def test_models_import_registers_all_tables():
    """Every table of the model package is known to Alembic's metadata."""
    expected = {
        "conversations",
        "messages",
        "usage_logs",
        "anonymous_sessions",
        "knowledge_base",
        "knowledge_namespaces",
    }
    assert expected <= set(Base.metadata.tables)

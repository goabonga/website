# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the alembic migration chain (rendered as offline SQL, no database needed)."""

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from custom_domain.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _config(buffer: io.StringIO | None = None) -> Config:
    config = Config(str(ALEMBIC_INI))
    if buffer is not None:
        config.output_buffer = buffer
    return config


def _upgrade_sql() -> str:
    buffer = io.StringIO()
    command.upgrade(_config(buffer), "head", sql=True)
    return buffer.getvalue()


class TestMigrationChain:
    """Tests for the revision graph."""

    def test_single_head(self):
        """The chain has exactly one head."""
        script = ScriptDirectory.from_config(_config())
        assert len(script.get_heads()) == 1

    def test_initial_revision_is_the_base(self):
        """The first revision has no parent."""
        script = ScriptDirectory.from_config(_config())
        revision = script.get_revision("001_initial")
        assert revision is not None
        assert revision.down_revision is None


class TestUpgradeSql:
    """Tests for the SQL rendered by the initial migration."""

    @pytest.mark.parametrize("table", sorted(Base.metadata.tables))
    def test_every_model_table_is_created(self, table):
        """Each table declared by the models is created by the migration."""
        assert f"CREATE TABLE {table} (" in _upgrade_sql()

    def test_domain_status_enum_values(self):
        """The domainstatus enum carries every DomainStatus value."""
        from custom_domain.models.enums import DomainStatus

        sql = _upgrade_sql()
        for status in DomainStatus:
            assert f"'{status.value}'" in sql

    def test_domain_uniqueness_ignores_soft_deleted_rows(self):
        """The unique index on domain only covers rows that are not deleted."""
        sql = _upgrade_sql()
        assert "CREATE UNIQUE INDEX ix_custom_domains_domain_unique" in sql
        assert "WHERE deleted_at IS NULL" in sql

    def test_downgrade_drops_everything(self):
        """Downgrading to base drops the tables and the enum."""
        buffer = io.StringIO()
        command.downgrade(_config(buffer), "head:base", sql=True)
        sql = buffer.getvalue()
        for table in Base.metadata.tables:
            assert f"DROP TABLE {table}" in sql
        assert "DROP TYPE domainstatus" in sql

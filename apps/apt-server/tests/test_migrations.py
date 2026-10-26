# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Alembic migrations render the catalog schema (offline, no database)."""

from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ALEMBIC_DIR = Path(__file__).resolve().parent.parent / "alembic"


@pytest.fixture
def alembic_config(monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", "postgresql+asyncpg://localhost/apt_server")
    config.output_buffer = StringIO()
    return config


def test_single_linear_history_from_001(alembic_config: Config) -> None:
    script = ScriptDirectory.from_config(alembic_config)

    revisions = [rev.revision for rev in script.walk_revisions()]

    assert revisions[-1] == "001"
    assert len(script.get_heads()) == 1


def test_upgrade_sql_creates_catalog_tables(alembic_config: Config) -> None:
    command.upgrade(alembic_config, "head", sql=True)

    sql = alembic_config.output_buffer.getvalue()
    for table in ("packages", "package_acl", "index_cache"):
        assert f"CREATE TABLE {table}" in sql
    assert "CREATE TYPE package_visibility" in sql
    assert "ck_package_acl_grantee_exclusive" in sql
    assert "uq_packages_identity" in sql


def test_downgrade_sql_drops_catalog_tables(alembic_config: Config) -> None:
    command.downgrade(alembic_config, "head:base", sql=True)

    sql = alembic_config.output_buffer.getvalue()
    for table in ("packages", "package_acl", "index_cache"):
        assert f"DROP TABLE {table}" in sql

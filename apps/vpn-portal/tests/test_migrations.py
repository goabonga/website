# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic migration chain.

The migrations are rendered as SQL for PostgreSQL (``upgrade --sql``): no database is needed.
"""

import io
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from vpn_portal.db.base import Base

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@pytest.fixture
def config() -> Config:
    return Config(str(ALEMBIC_INI))


def render(config: Config, command_name: str, *args) -> str:
    buffer = io.StringIO()
    config.output_buffer = buffer
    getattr(command, command_name)(config, *args, sql=True)
    return buffer.getvalue()


def test_single_linear_history(config):
    script = ScriptDirectory.from_config(config)

    assert len(script.get_heads()) == 1
    revisions = [revision.revision for revision in script.walk_revisions()]
    assert revisions[-1] == "001"
    assert len(revisions) == len(set(revisions))


def test_upgrade_creates_the_certificates_table(config):
    sql = render(config, "upgrade", "head")

    assert "CREATE TABLE vpn_certificates" in sql
    assert "scopes VARCHAR(64)[] NOT NULL" in sql
    assert "CONSTRAINT pk_vpn_certificates PRIMARY KEY (id)" in sql
    assert "CONSTRAINT uq_vpn_certificates_serial_number UNIQUE (serial_number)" in sql


def test_upgrade_creates_the_indexes(config):
    sql = render(config, "upgrade", "head")

    for column in ("user_id", "serial_number", "common_name", "not_after", "revoked_at"):
        assert f"CREATE INDEX ix_vpn_certificates_{column} ON vpn_certificates ({column})" in sql


def test_upgrade_covers_every_model_column(config):
    sql = render(config, "upgrade", "head")
    table_sql = sql.split("CREATE TABLE vpn_certificates", 1)[1].split(");", 1)[0]

    for column in Base.metadata.tables["vpn_certificates"].c:
        assert f"\n    {column.name} " in table_sql, column.name


def test_downgrade_drops_the_table(config):
    sql = render(config, "downgrade", "head:base")

    assert "DROP TABLE vpn_certificates" in sql
    assert "DROP INDEX ix_vpn_certificates_user_id" in sql

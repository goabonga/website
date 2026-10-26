# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic migrations: the chain is linear and renders valid DDL offline."""

import io
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from team.models import Base

ALEMBIC_DIR = Path(__file__).resolve().parents[1] / "alembic"


def _config() -> Config:
    config = Config()
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    return config


def _schema_revisions() -> list:
    """Revisions that create tables, oldest first (data migrations are excluded)."""
    scripts = ScriptDirectory.from_config(_config())
    revisions = [r for r in scripts.walk_revisions() if re.match(r"\d+ create", r.doc)]
    return list(reversed(revisions))


def test_single_head_and_linear_history():
    scripts = ScriptDirectory.from_config(_config())
    assert len(scripts.get_heads()) == 1
    for revision in scripts.walk_revisions():
        assert not isinstance(revision.down_revision, tuple)


def test_every_revision_has_a_downgrade():
    scripts = ScriptDirectory.from_config(_config())
    for revision in scripts.walk_revisions():
        assert callable(getattr(revision.module, "downgrade", None)), revision.revision


def test_schema_revisions_render_a_table_for_every_model():
    config = _config()
    buffer = io.StringIO()
    config.output_buffer = buffer
    command.upgrade(config, f"{_schema_revisions()[-1].revision}", sql=True)
    sql = buffer.getvalue()
    for table in Base.metadata.tables:
        assert f"CREATE TABLE {table} " in sql, table


def test_downgrade_drops_every_table():
    config = _config()
    buffer = io.StringIO()
    config.output_buffer = buffer
    last = _schema_revisions()[-1].revision
    command.downgrade(config, f"{last}:base", sql=True)
    sql = buffer.getvalue()
    for table in Base.metadata.tables:
        assert f"DROP TABLE {table}" in sql, table

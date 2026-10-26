# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the Alembic environment and revisions."""

from pathlib import Path

import analytics
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

APP_DIR = Path(analytics.__file__).resolve().parents[2]


@pytest.fixture
def alembic_config():
    config = Config(str(APP_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(APP_DIR / "alembic"))
    return config


class TestRevisions:
    """Tests for the revision chain."""

    def test_single_head(self, alembic_config):
        script = ScriptDirectory.from_config(alembic_config)
        assert len(script.get_heads()) == 1

    def test_revisions_are_linear(self, alembic_config):
        script = ScriptDirectory.from_config(alembic_config)
        revisions = [rev.revision for rev in script.walk_revisions()]
        assert revisions == sorted(revisions, reverse=True)
        assert revisions[-1] == "001"


class TestOfflineUpgrade:
    """Render the migrations as SQL, without a database."""

    @pytest.fixture
    def sql(self, alembic_config, monkeypatch, capsys):
        from alembic import command

        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/analytics")
        command.upgrade(alembic_config, "head", sql=True)
        return capsys.readouterr().out

    def test_creates_sessions_and_events(self, sql):
        assert "CREATE TABLE analytics_sessions" in sql
        assert "CREATE TABLE analytics_events" in sql

    def test_creates_indexes(self, sql):
        assert "CREATE UNIQUE INDEX ix_analytics_sessions_session_id" in sql
        assert "CREATE INDEX ix_analytics_events_type_timestamp" in sql

    def test_events_cascade_with_session(self, sql):
        assert "REFERENCES analytics_sessions (id) ON DELETE CASCADE" in sql

    def test_stamps_head_version(self, sql):
        assert "alembic_version" in sql
        assert "'001'" in sql

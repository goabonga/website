# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the database migrations feature."""

import io
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from behave import given, then, when

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@given("the Alembic configuration of the application")
def step_config(context):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/migrations"
    context.add_cleanup(_restore_url, previous)
    context.alembic_config = Config(str(ALEMBIC_INI))
    context.scripts = ScriptDirectory.from_config(context.alembic_config)


def _restore_url(previous):
    if previous is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = previous


@then('the migration history should have the single head "{revision}"')
def step_head(context, revision):
    assert context.scripts.get_heads() == [revision]


@then("the migration history should contain {count:d} revisions")
def step_count(context, count):
    assert len(list(context.scripts.walk_revisions())) == count


@when("the upgrade to head is rendered as SQL")
def step_render(context):
    buffer = io.StringIO()
    context.alembic_config.output_buffer = buffer
    command.upgrade(context.alembic_config, "head", sql=True)
    context.sql = buffer.getvalue()


@then("the SQL should create the tables:")
def step_creates(context):
    for row in context.table:
        assert f"CREATE TABLE {row['table']} " in context.sql, row["table"]


@then('the SQL should drop the table "{table}"')
def step_drops(context, table):
    assert f"DROP TABLE {table}" in context.sql


@then('the SQL should record the revision "{revision}"')
def step_records(context, revision):
    assert f"UPDATE alembic_version SET version_num='{revision}'" in context.sql

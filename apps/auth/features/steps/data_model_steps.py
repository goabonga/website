# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the data model and migrations feature."""

import re
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from behave import given, then, when
from sqlalchemy import inspect
from sqlalchemy.orm import configure_mappers
from sqlite_db import Database

APP_DIR = Path(__file__).resolve().parents[2]


@given("the SQLAlchemy models are imported")
def step_import_models(context):
    import auth.db.models  # noqa: F401
    from auth.db.base import Base

    context.metadata = Base.metadata


@given("the Alembic migration scripts")
def step_load_scripts(context):
    config = Config(str(APP_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(APP_DIR / "alembic"))
    context.script = ScriptDirectory.from_config(config)


@when("the ORM mappers are configured")
def step_configure_mappers(context):
    context.mapping_error = None
    try:
        configure_mappers()
    except Exception as exc:
        context.mapping_error = exc


@when("the schema is created on an in-memory SQLite database")
def step_create_schema(context):
    database = Database()
    context.add_cleanup(database.dispose)
    context.engine = database.engine


@then("the metadata declares {count:d} tables")
def step_table_count(context, count):
    assert len(context.metadata.tables) == count, sorted(context.metadata.tables)


@then('the metadata declares the tables "{names}"')
def step_declared_tables(context, names):
    missing = [n.strip() for n in names.split(",") if n.strip() not in context.metadata.tables]
    assert not missing, f"missing tables: {missing}"


@then("no mapping error is raised")
def step_no_mapping_error(context):
    assert context.mapping_error is None, context.mapping_error


@then("{count:d} tables exist in the database")
def step_database_tables(context, count):
    names = inspect(context.engine).get_table_names()
    assert len(names) == count, names


@then("every foreign key points to an existing table")
def step_foreign_keys(context):
    inspector = inspect(context.engine)
    names = set(inspector.get_table_names())
    for table in names:
        for fk in inspector.get_foreign_keys(table):
            assert fk["referred_table"] in names, (table, fk)


@then("the history has exactly one head")
def step_single_head(context):
    heads = context.script.get_heads()
    assert len(heads) == 1, heads


@then("the history has {count:d} revisions")
def step_revision_count(context, count):
    revisions = list(context.script.walk_revisions())
    assert len(revisions) == count, len(revisions)


@then("every revision can be upgraded and downgraded")
def step_reversible(context):
    for revision in context.script.walk_revisions():
        module = revision.module
        assert callable(getattr(module, "upgrade", None)), revision.revision
        assert callable(getattr(module, "downgrade", None)), revision.revision


@then("the tables created by the migrations are the tables of the models")
def step_migrations_match_models(context):
    created = set()
    for path in (APP_DIR / "alembic" / "versions").glob("*.py"):
        upgrade_source = path.read_text().split("def downgrade")[0]
        created |= set(re.findall(r"create_table\(\s*[\"'](\w+)[\"']", upgrade_source))
    assert created == set(context.metadata.tables), created ^ set(context.metadata.tables)


@then('the head is the revision "{revision}"')
def step_head_revision(context, revision):
    assert context.script.get_heads() == [revision], context.script.get_heads()


@then("no migration inserts a row")
def step_no_seed(context):
    versions = APP_DIR / "alembic" / "versions"
    pattern = re.compile(
        r"INSERT\s+INTO\s+(scopes|role_scopes|roles|oauth2_clients|tenants)\b", re.I
    )
    offenders = [p.name for p in sorted(versions.glob("*.py")) if pattern.search(p.read_text())]
    assert not offenders, offenders

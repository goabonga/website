# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the data model and migrations feature."""

import io
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from alembic.script import ScriptDirectory
from behave import given, then, when

from alembic import command
from knowledge.models import Base, Collection, Organization
from knowledge.models.enums import OwnerType, PlanType

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


@when("I load the migration history")
def step_load_history(context):
    context.script = ScriptDirectory.from_config(_alembic_config())


@then('the migration history should have a single head "{revision}"')
def step_single_head(context, revision):
    assert context.script.get_heads() == [revision], context.script.get_heads()


@then("the migration history should contain {count:d} revisions")
def step_revision_count(context, count):
    revisions = list(context.script.walk_revisions())
    assert len(revisions) == count, len(revisions)


@when('I render the SQL of the migrations up to "{end}"')
def step_render_sql(context, end):
    config = _alembic_config()
    config.output_buffer = io.StringIO()
    command.upgrade(config, f"base:{end}", sql=True)
    context.sql = config.output_buffer.getvalue()


@then("the SQL should create the pgvector extension")
def step_sql_extension(context):
    assert "CREATE EXTENSION IF NOT EXISTS vector" in context.sql


@then('the SQL should create the table "{table}"')
def step_sql_table(context, table):
    assert f"CREATE TABLE {table} " in context.sql, f"{table} not created"


@then("the model metadata should declare the tables")
def step_metadata_tables(context):
    expected = {row["table"] for row in context.table}
    assert expected == set(Base.metadata.tables), set(Base.metadata.tables) ^ expected


@given('a collection owned by a "{owner_type}"')
def step_collection(context, owner_type):
    context.collection = Collection(
        owner_type=OwnerType(owner_type),
        owner_id=uuid4(),
        name="Docs",
        slug="docs",
    )


@then("the collection should be personal")
def step_collection_personal(context):
    assert context.collection.is_personal


@then("the collection should not be organization owned")
def step_collection_not_org(context):
    assert not context.collection.is_organization_owned


@then("the collection should be organization owned")
def step_collection_org(context):
    assert context.collection.is_organization_owned


@given('an organization on the "{plan}" plan')
def step_organization(context, plan):
    context.organization = Organization(name="Acme", slug="acme", plan=PlanType(plan))


@then("the organization can use a custom domain")
def step_org_custom_domain(context):
    assert context.organization.can_use_custom_domain


@then("the organization cannot use a custom domain")
def step_org_no_custom_domain(context):
    assert not context.organization.can_use_custom_domain

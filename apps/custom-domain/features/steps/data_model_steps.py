# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the data model feature."""

import io
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from behave import given, then, when
from custom_domain.models import CustomDomain
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _new_domain(name, client_id):
    return CustomDomain(
        domain=name,
        client_id=client_id,
        owner_id="org_1",
        owner_type="organization",
        upstream_target="unix:/run/app.sock",
        cname_target="apps.example.com",
    )


@when("I render the SQL of the alembic upgrade to head")
def step_render_upgrade(context):
    buffer = io.StringIO()
    config = Config(str(ALEMBIC_INI))
    config.output_buffer = buffer
    command.upgrade(config, "head", sql=True)
    context.sql = buffer.getvalue()


@when("I render the SQL of the alembic downgrade to base")
def step_render_downgrade(context):
    buffer = io.StringIO()
    config = Config(str(ALEMBIC_INI))
    config.output_buffer = buffer
    command.downgrade(config, "head:base", sql=True)
    context.sql = buffer.getvalue()


@then('the SQL creates the table "{table}"')
def step_sql_creates(context, table):
    assert f"CREATE TABLE {table} (" in context.sql


@then('the SQL drops the table "{table}"')
def step_sql_drops(context, table):
    assert f"DROP TABLE {table}" in context.sql


@given('a stored domain "{name}" owned by client "{client_id}"')
def step_stored_domain(context, name, client_id):
    with context.db.session() as session:
        session.add(_new_domain(name, client_id))
        session.commit()


@given('the domain "{name}" is soft-deleted')
def step_soft_delete(context, name):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        domain.deleted_at = datetime.now(UTC)
        session.commit()


@then('the stored domain "{name}" has the status "{status}"')
def step_domain_status(context, name, status):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        assert domain.status.value == status


@then('the stored domain "{name}" has {count:d} retries')
def step_domain_retries(context, name, count):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        assert domain.retry_count == count


@when('I register the domain "{name}" again for client "{client_id}"')
def step_register_again(context, name, client_id):
    context.registration_error = None
    with context.db.session() as session:
        session.add(_new_domain(name, client_id))
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            context.registration_error = error


@then("the registration succeeds")
def step_registration_ok(context):
    assert context.registration_error is None


@then("the registration is rejected as a duplicate")
def step_registration_rejected(context):
    assert context.registration_error is not None

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the account and organisation settings pages feature."""

import asyncio
import json
from unittest.mock import MagicMock, patch

from auth.db.models.tenant import Tenant, TenantCustomRole
from auth.db.models.user import User, UserEmail
from auth.services.session import SessionService
from auth.tasks import custom_domain
from behave import given, then, when
from organisation_api_steps import _tenant
from sqlalchemy import func, select

SESSION_COOKIE = "session"


def _user(context, email):
    return context.database.sync_session.scalars(
        select(User).join(UserEmail).where(func.lower(UserEmail.email) == email.lower())
    ).one()


# ------------------------------------------------------------------ fixtures
@given('"{email}" is signed in')
def step_signed_in(context, email):
    token, _csrf = asyncio.run(
        SessionService().create_session(context.db, str(_user(context, email).id))
    )
    context.database.commit()
    context.session_token = token
    context.client.cookies.set(SESSION_COOKIE, token)


@given('the organisation "{slug}" has a role "{name}" granting "{scopes}"')
def step_org_role(context, slug, name, scopes):
    context.database.sync_session.add(
        TenantCustomRole(
            tenant_id=_tenant(context, slug).id,
            name=name,
            display_name=name.title(),
            scopes=scopes.split(),
        )
    )
    context.database.commit()


@given("the custom domain tasks are not sent to a broker")
def step_domain_tasks_not_queued(context):
    context.domain_tasks = MagicMock()
    for task in (custom_domain.verify_custom_domain_dns, custom_domain.remove_custom_domain_config):
        patcher = patch.object(task, "delay", context.domain_tasks)
        patcher.start()
        context.add_cleanup(patcher.stop)


# ------------------------------------------------------------------ requests
@when('I open the settings page "{path}"')
def step_open(context, path):
    context.response = context.client.get(path, follow_redirects=False)


@when('I send the settings request "{method}" "{path}" with the JSON body')
def step_send_json(context, method, path):
    context.response = context.client.request(
        method, path, json=json.loads(context.text), follow_redirects=False
    )
    if method == "POST" and context.response.status_code == 201:
        context.created_token_id = context.response.json()["pat"]["id"]


@when('I submit the settings form "{path}" with')
def step_submit_form(context, path):
    data = {row["field"]: row["value"] for row in context.table}
    context.response = context.client.post(path, data=data, follow_redirects=False)


@when('I open the page "{suffix}" of the organisation "{slug}" settings')
def step_open_org(context, suffix, slug):
    path = f"/auth/settings/org/{_tenant(context, slug).id}{suffix}"
    context.response = context.client.get(path, follow_redirects=False)


@when('I open the overview of the organisation "{slug}" settings')
def step_open_overview(context, slug):
    context.response = context.client.get(
        f"/auth/settings/org/{_tenant(context, slug).id}", follow_redirects=False
    )


@when('I submit the form "{suffix}" of the organisation "{slug}" settings with')
def step_submit_org_form(context, suffix, slug):
    data = {row["field"]: row["value"] for row in context.table}
    path = f"/auth/settings/org/{_tenant(context, slug).id}{suffix}"
    context.response = context.client.post(path, data=data, follow_redirects=False)


@when("I revoke the personal access token created from the settings")
def step_revoke_token(context):
    context.response = context.client.delete(
        f"/auth/settings/tokens/api/{context.created_token_id}", follow_redirects=False
    )


# ---------------------------------------------------------------- assertions
@then('the settings page "<path>" is displayed for each of')
def step_pages_displayed(context):
    for row in context.table:
        response = context.client.get(row["path"], follow_redirects=False)
        assert response.status_code == 200, (row["path"], response.status_code)


@then('the organisation "{slug}" is named "{name}"')
def step_org_named(context, slug, name):
    context.database.sync_session.expire_all()
    tenant = context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()
    assert tenant.display_name == name, tenant.display_name


def _org(context, slug):
    context.database.sync_session.expire_all()
    return context.database.sync_session.scalars(select(Tenant).where(Tenant.slug == slug)).one()


@then('the organisation "{slug}" has the custom domain "{domain}"')
def step_org_domain(context, slug, domain):
    assert _org(context, slug).custom_domain == domain, _org(context, slug).custom_domain


@then('the organisation "{slug}" has no custom domain')
def step_org_no_domain(context, slug):
    assert _org(context, slug).custom_domain is None, _org(context, slug).custom_domain


@then("the DNS verification of the custom domain is queued")
def step_verification_queued(context):
    context.domain_tasks.assert_called_once()


@then("no custom domain task is queued")
def step_no_domain_task(context):
    context.domain_tasks.assert_not_called()


@then("the response lists {count:d} sessions")
def step_lists_sessions(context, count):
    payload = context.response.json()
    items = payload["sessions"] if isinstance(payload, dict) else payload
    assert len(items) == count, payload


@then("the response carries a new personal access token")
def step_new_token(context):
    assert context.response.json()["token"].startswith("gab_pat_"), context.response.text[:200]


@then('the response lists the token "{name}"')
def step_lists_token(context, name):
    payload = context.response.json()
    items = payload["tokens"] if isinstance(payload, dict) else payload
    assert name in [item["name"] for item in items], payload


@then("the removal of the custom domain configuration is queued")
def step_removal_queued(context):
    """The last task sent is the removal of the configuration: (domain, slug), no tenant id."""
    assert len(context.domain_tasks.call_args.args) == 2, context.domain_tasks.call_args

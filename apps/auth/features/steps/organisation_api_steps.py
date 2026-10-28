# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the organisation API feature."""

import asyncio
import json
from unittest.mock import MagicMock, patch

from api_support import _send, _user
from auth.db.models.tenant import Tenant, TenantCustomRole, TenantMember, WebhookDelivery
from auth.services.pat import PersonalAccessTokenService
from auth.services.tenant import tenant_service
from behave import given, then, when
from helpers import patch_setting
from sqlalchemy import select


def _session(context):
    return context.database.sync_session


def _tenant(context, slug):
    return _session(context).scalars(select(Tenant).where(Tenant.slug == slug)).one()


def _role(context, slug, name):
    return (
        _session(context)
        .scalars(
            select(TenantCustomRole).where(
                TenantCustomRole.tenant_id == _tenant(context, slug).id,
                TenantCustomRole.name == name,
            )
        )
        .one()
    )


def _membership(context, email, slug):
    return (
        _session(context)
        .scalars(
            select(TenantMember).where(
                TenantMember.tenant_id == _tenant(context, slug).id,
                TenantMember.user_id == _user(context, email).id,
            )
        )
        .one_or_none()
    )


def _org_path(context, slug, suffix=""):
    # The webhook endpoints exist only under the organisation prefix, not under /me.
    prefix = "organisations" if suffix.startswith("/webhooks") else "me/organisations"
    return f"/api/v1/{prefix}/{_tenant(context, slug).id}{suffix}"


def _token(context, email):
    _pat, raw = asyncio.run(
        PersonalAccessTokenService().create_token(
            context.db, user_id=_user(context, email).id, name="behave", scopes=["me:read"]
        )
    )
    context.database.commit()
    context.bearer = raw


# ------------------------------------------------------------------ fixtures
@given('"{email}" owns the organisation "{slug}"')
def step_owns_organisation(context, email, slug):
    asyncio.run(
        tenant_service.create_organisation_with_owner(
            context.db, slug=slug, display_name=slug.title(), owner_user_id=_user(context, email).id
        )
    )
    context.database.commit()
    _token(context, email)


@given('"{email}" is a member of the organisation "{slug}" with the role "{role}"')
def step_is_member_given(context, email, slug, role):
    tenant = _tenant(context, slug)
    _session(context).add(
        TenantMember(
            tenant_id=tenant.id,
            user_id=_user(context, email).id,
            role_id=_role(context, slug, role).id,
        )
    )
    context.database.commit()


@given('the organisation "{slug}" has the custom domain "{domain}"')
def step_org_has_domain(context, slug, domain):
    _tenant(context, slug).custom_domain = domain
    context.database.commit()


@given("webhook deliveries are not sent to a broker")
def step_deliveries_not_queued(context):
    from auth.tasks import webhooks as webhook_tasks

    patcher = patch.object(webhook_tasks.deliver_webhook, "delay", MagicMock())
    patcher.start()
    context.add_cleanup(patcher.stop)


@given("webhook targets may be private")
def step_private_targets(context):
    patch_setting(context, "webhook_allow_private_networks", True)


# ------------------------------------------------------------------ requests
@when('I GET the members of the organisation "{slug}"')
def step_get_members(context, slug):
    _send(context, "GET", _org_path(context, slug, "/members/"))


@when('I add "{email}" to the organisation "{slug}" with the role "{role}"')
def step_add_member(context, email, slug, role):
    body = {"user_id": str(_user(context, email).id), "role_id": str(_role(context, slug, role).id)}
    _send(context, "POST", _org_path(context, slug, "/members/"), body=body)


@when('I remove "{email}" from the organisation "{slug}"')
def step_remove_member(context, email, slug):
    _send(context, "DELETE", _org_path(context, slug, f"/members/{_user(context, email).id}"))


@when('I GET the organisation "{slug}" sub-path "{suffix}"')
def step_get_sub_path(context, slug, suffix):
    _send(context, "GET", _org_path(context, slug, suffix))


@when('I {method} the organisation "{slug}" sub-path "{suffix}" with the JSON body')
def step_send_sub_path(context, method, slug, suffix):
    _send(context, method, _org_path(context, slug, suffix), body=json.loads(context.text))


def _prefixed_path(context, slug, suffix, prefix):
    return f"/api/v1/{prefix}/{_tenant(context, slug).id}{suffix}"


@when('I {method:Method} the sub-path "{suffix}" of the organisation "{slug}" under "{prefix}"')
def step_send_prefixed(context, method, suffix, slug, prefix):
    _send(context, method, _prefixed_path(context, slug, suffix, prefix))


@when(
    'I {method:Method} the sub-path "{suffix}" of the organisation "{slug}" under "{prefix}" '
    "with the JSON body"
)
def step_send_prefixed_body(context, method, suffix, slug, prefix):
    body = json.loads(context.text)
    _send(context, method, _prefixed_path(context, slug, suffix, prefix), body=body)


# ---------------------------------------------------------------- assertions
@then('"{email}" is a member of the organisation "{slug}" with the role "{role}"')
def step_is_member(context, email, slug, role):
    member = _membership(context, email, slug)
    assert member is not None and member.custom_role.name == role, member


@then('"{email}" is not a member of the organisation "{slug}"')
def step_is_not_member(context, email, slug):
    assert _membership(context, email, slug) is None


@then('the organisation "{slug}" includes the roles "{names}"')
def step_org_roles(context, slug, names):
    roles = (
        _session(context)
        .scalars(
            select(TenantCustomRole.name).where(
                TenantCustomRole.tenant_id == _tenant(context, slug).id
            )
        )
        .all()
    )
    assert set(names.split(", ")) <= set(roles), roles


@then("the organisation has {count:d} member")
@then("the organisation has {count:d} members")
def step_member_count(context, count):
    assert context.response.json()["total"] == count, context.response.text[:200]


@then('the response lists the organisation "{slug}"')
def step_lists_organisation(context, slug):
    payload = context.response.json()
    slugs = [item["slug"] for item in (payload["items"] if isinstance(payload, dict) else payload)]
    assert slug in slugs, slugs


@then('the response lists the role "{name}"')
def step_lists_role(context, name):
    payload = context.response.json()
    items = payload["items"] if isinstance(payload, dict) else payload
    assert name in [item["name"] for item in items], payload


@then('the response JSON path "{path}" is "{value}"')
def step_json_path(context, path, value):
    node = context.response.json()
    for part in path.split("."):
        node = node[part]
    assert str(node) == value, f"{path}: expected {value!r}, got {node!r}"


@then('the response JSON field "groups" lists the event "{event}"')
def step_events_catalog(context, event):
    events = [e for group in context.response.json()["groups"].values() for e in group]
    assert event in events, events


@then("the response contains a webhook secret")
def step_webhook_secret(context):
    assert context.response.json()["secret"], context.response.text[:200]


@then('a "{event}" webhook delivery is queued for the organisation "{slug}"')
def step_delivery_queued(context, event, slug):
    context.database.sync_session.expire_all()
    deliveries = (
        _session(context)
        .scalars(
            select(WebhookDelivery).where(
                WebhookDelivery.tenant_id == _tenant(context, slug).id,
                WebhookDelivery.event == event,
            )
        )
        .all()
    )
    assert len(deliveries) == 1, deliveries
    assert deliveries[0].request_body["data"]["custom_domain"], deliveries[0].request_body

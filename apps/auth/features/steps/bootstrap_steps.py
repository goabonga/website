# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the platform bootstrap."""

import json
import uuid

from auth.db.models.oauth2 import OAuth2Client
from auth.db.models.tenant import Tenant, TenantBranding, TenantCustomRole, TenantMember
from auth.db.models.user import UserEmail
from behave import given, register_type, then
from cli_support import run_command
from helpers import patch_setting
from parse import with_pattern
from sqlalchemy import func, select


@with_pattern(r"[\[{].*[\]}]")
def parse_json(text):
    return json.loads(text)


register_type(json=parse_json)


@given('the setting "{name}" is "{value}"')
def step_setting_text(context, name, value):
    patch_setting(context, name, value)


@given('the setting "{name}" is {value:json}')
def step_setting_json(context, name, value):
    patch_setting(context, name, value)


@given("the platform tenant branding is {value:json}")
def step_branding(context, value):
    patch_setting(context, "platform_tenant_branding", value)


@given("the bootstrap was run")
def step_bootstrap_run(context):
    run_command(context, "auth bootstrap")
    assert context.command_status == 0, context.command_stderr


@given('a verified user "{email}" with the password "{password}" registered on the platform tenant')
def step_user_on_platform(context, email, password):
    from factories import make_user

    session = context.database.sync_session
    platform = _platform(context)
    make_user(session, email, password, registration_tenant_id=platform.id)
    context.database.commit()


def _platform(context):
    return context.database.sync_session.scalars(
        select(Tenant).where(Tenant.is_platform.is_(True))
    ).one()


@then('the platform tenant is "{slug}" named "{name}"')
def step_platform_tenant_named(context, slug, name):
    tenant = _platform(context)
    assert (tenant.slug, tenant.display_name) == (slug, name)


@then('the platform tenant is "{slug}" named "{name}", open to all users and active')
def step_platform_tenant(context, slug, name):
    step_platform_tenant_named(context, slug, name)
    tenant = _platform(context)
    assert tenant.trust_mode.value == "all" and tenant.is_active is True


@then('the platform tenant has the roles "{names}"')
def step_platform_roles(context, names):
    session = context.database.sync_session
    roles = session.scalars(
        select(TenantCustomRole.name).where(TenantCustomRole.tenant_id == _platform(context).id)
    ).all()
    assert sorted(roles) == sorted(names.split(", ")), roles


@then('the platform tenant has the primary colour "{colour}"')
def step_platform_colour(context, colour):
    branding = context.database.sync_session.scalars(
        select(TenantBranding).where(TenantBranding.tenant_id == _platform(context).id)
    ).one()
    assert branding.primary_color == colour


@then('the platform tenant has the identifier "{identifier}"')
def step_platform_id(context, identifier):
    assert _platform(context).id == uuid.UUID(identifier)


@then("there is exactly {count:d} platform tenant")
def step_platform_count(context, count):
    session = context.database.sync_session
    total = session.scalar(select(func.count()).select_from(Tenant).where(Tenant.is_platform))
    assert total == count, total


@then("there is no platform tenant")
def step_no_platform(context):
    session = context.database.sync_session
    total = session.scalar(select(func.count()).select_from(Tenant).where(Tenant.is_platform))
    assert total == 0, total


@then('"{email}" is registered on the platform tenant and is a "{role}" of it')
def step_registered_member(context, email, role):
    session = context.database.sync_session
    platform = _platform(context)
    user_id = session.scalars(select(UserEmail.user_id).where(UserEmail.email == email)).one()
    from auth.db.models.user import User

    assert session.get(User, user_id).registration_tenant_id == platform.id
    member = session.scalars(
        select(TenantMember).where(
            TenantMember.tenant_id == platform.id, TenantMember.user_id == user_id
        )
    ).one()
    assert member.custom_role.name == role


def _client(context, client_id):
    return context.database.sync_session.scalars(
        select(OAuth2Client).where(OAuth2Client.client_id == client_id)
    ).one()


@then('the client "{client_id}" is a public client that requires PKCE and no consent')
def step_client_public(context, client_id):
    client = _client(context, client_id)
    assert (client.is_confidential, client.require_pkce, client.require_consent) == (
        False,
        True,
        False,
    )
    assert client.token_endpoint_auth_method == "none" and client.client_secret_hash is None


@then('the client "{client_id}" redirects to "{uri}"')
def step_client_redirect(context, client_id, uri):
    assert _client(context, client_id).redirect_uris == [uri]

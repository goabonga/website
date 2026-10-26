# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for the multi-tenancy and OIDC discovery feature."""

import asyncio
import dataclasses
import json

from auth.db.models.tenant import (
    CustomDomainStatus,
    Tenant,
    TenantCustomRole,
    TenantMember,
    TenantTrustedSource,
    TenantTrustMode,
)
from auth.middlewares.tenant import (
    TenantContext,
    TenantMiddleware,
    get_csrf_cookie_name,
    get_session_cookie_domain,
    get_session_cookie_name,
    set_tenant_context,
)
from auth.services.branding import BrandingConfig
from auth.services.issuer import get_tenant_issuer
from auth.services.tenant import tenant_service
from auth.services.trust import TrustPolicyService
from behave import given, then, when
from factories import make_tenant, make_user
from helpers import patch_setting
from sqlalchemy import select
from sqlite_db import use_database


# ---------------------------------------------------------------- discovery
@given('the issuer is configured as "{issuer}"')
def step_configure_issuer(context, issuer):
    patch_setting(context, "issuer", issuer)


@given('the tenant base domain is "{domain}"')
def step_base_domain(context, domain):
    patch_setting(context, "tenant_base_domain", domain)


# ------------------------------------------------------------ issuer per tenant
@given('a {kind} tenant with slug "{slug}" and custom domain "{domain}"')
def step_tenant(context, kind, slug, domain):
    domain = "" if domain == "-" else domain
    context.tenant = Tenant(
        slug=slug,
        display_name=slug.title(),
        is_platform=kind == "platform",
        custom_domain=domain or None,
        custom_domain_status=CustomDomainStatus.ACTIVE if domain else None,
    )


@when("the issuer of the tenant is computed")
def step_compute_issuer(context):
    context.issuer = asyncio.run(get_tenant_issuer(context.db, context.tenant))


@then('the issuer is "{issuer}"')
def step_issuer(context, issuer):
    assert context.issuer == issuer, context.issuer


# ------------------------------------------------------- tenant middleware
async def _echo_app(scope, receive, send):
    """Tiny ASGI application that reports what the middleware attached to the scope."""
    tenant = scope.get("tenant")
    body = json.dumps(
        {
            "path": scope["path"],
            "tenant": dataclasses.asdict(tenant) if tenant else None,
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


@given('the tenant middleware serves the base domain "{domain}"')
def step_middleware(context, domain):
    use_database(context)
    context.mw_base_domain = domain


@given('the tenant "{slug}" exists')
def step_tenant_exists(context, slug):
    make_tenant(context.database.sync_session, slug)
    context.database.commit()


@given('the tenant "{slug}" exists with the custom domain "{domain}"')
def step_tenant_with_domain(context, slug, domain):
    make_tenant(context.database.sync_session, slug, custom_domain=domain)
    context.database.commit()


@given('the platform tenant "{slug}" exists')
def step_platform_exists(context, slug):
    make_tenant(context.database.sync_session, slug, platform=True)
    context.database.commit()


@when('I request "{path}" on the host "{host}"')
def step_request_on_host(context, path, host):
    app = TenantMiddleware(_echo_app, base_domain=context.mw_base_domain)
    client = context.client_class(app, base_url=f"http://{host}")
    context.response = client.get(path, follow_redirects=False)
    client.close()


@then('the request is attributed to the tenant "{slug}" by "{method}"')
def step_attributed(context, slug, method):
    tenant = context.response.json()["tenant"]
    assert tenant is not None, context.response.text
    assert (tenant["tenant_slug"], tenant["resolution_method"]) == (slug, method), tenant


@then('the application sees the path "{path}"')
def step_application_path(context, path):
    assert context.response.json()["path"] == path


@then('the client is redirected to "{location}"')
def step_redirected(context, location):
    assert context.response.status_code == 302, context.response.status_code
    assert context.response.headers["location"] == location


# ----------------------------------------------------------------- cookies
@when('the request context is the tenant "{slug}" resolved by "{method}"')
def step_request_context(context, slug, method):
    set_tenant_context(TenantContext(tenant_slug=slug, resolution_method=method))
    context.add_cleanup(set_tenant_context, None)


@then('the session cookie is named "{name}"')
def step_session_cookie(context, name):
    assert get_session_cookie_name() == name


@then('the CSRF cookie is named "{name}"')
def step_csrf_cookie(context, name):
    assert get_csrf_cookie_name() == name


@then('the cookie domain is "{domain}"')
def step_cookie_domain(context, domain):
    assert get_session_cookie_domain() == domain


@then("the cookie domain is not set")
def step_cookie_domain_unset(context):
    assert get_session_cookie_domain() is None


# ------------------------------------------------------ organisation creation
@given("a registered user")
def step_registered_user(context):
    use_database(context)
    context.user = make_user(context.database.sync_session)
    context.database.commit()


@when('the user creates the organisation "{slug}"')
def step_create_organisation(context, slug):
    context.organisation, context.membership = asyncio.run(
        tenant_service.create_organisation_with_owner(
            context.db, slug=slug, display_name=slug.title(), owner_user_id=context.user.id
        )
    )
    context.database.commit()


@then('the organisation has the roles "{names}"')
def step_organisation_roles(context, names):
    roles = context.database.sync_session.scalars(
        select(TenantCustomRole).where(TenantCustomRole.tenant_id == context.organisation.id)
    )
    assert {role.name for role in roles} == set(names.split(", "))


@then('the user is a member with the role "{name}"')
def step_member_role(context, name):
    member = context.database.sync_session.scalars(
        select(TenantMember).where(TenantMember.user_id == context.user.id)
    ).one()
    assert member.custom_role.name == name


@then('creating the organisation "{slug}" again is refused')
def step_create_again(context, slug):
    try:
        asyncio.run(
            tenant_service.create_organisation_with_owner(
                context.db, slug=slug, display_name=slug.title(), owner_user_id=context.user.id
            )
        )
    except ValueError as exc:
        assert "Slug already exists" in str(exc)
        return
    raise AssertionError("the duplicate slug was accepted")


# ------------------------------------------------------------ trust policy
@given('a tenant with the trust mode "{mode}"')
def step_trust_tenant(context, mode):
    use_database(context)
    session = context.database.sync_session
    context.trust_target = make_tenant(session, "target", trust_mode=TenantTrustMode(mode))
    context.trusted_tenant = make_tenant(session, "trusted")
    context.other_tenant = make_tenant(session, "other")
    session.add(
        TenantTrustedSource(
            tenant_id=context.trust_target.id, trusted_tenant_id=context.trusted_tenant.id
        )
    )
    session.commit()


@given("a user registered on the {origin} tenant who is {membership}")
def step_trust_user(context, origin, membership):
    session = context.database.sync_session
    registered_on = {
        "same": context.trust_target,
        "trusted": context.trusted_tenant,
        "another": context.other_tenant,
    }[origin]
    context.trust_user = make_user(session, registration_tenant_id=registered_on.id)
    if membership == "a member":
        session.add(TenantMember(tenant_id=context.trust_target.id, user_id=context.trust_user.id))
    session.commit()


@when("the sign-in is evaluated")
def step_evaluate_sign_in(context):
    context.allowed, context.reason = asyncio.run(
        TrustPolicyService().can_user_access_tenant(
            context.db, context.trust_user, context.trust_target.id
        )
    )


@then("the sign-in is {decision}")
def step_sign_in_decision(context, decision):
    assert context.allowed == (decision == "allowed"), (context.allowed, context.reason)


# ---------------------------------------------------------------- branding
@when("the branding of a missing tenant is requested")
def step_default_branding(context):
    context.branding = BrandingConfig.from_tenant(None)


@then('the branding uses the primary color "{color}"')
def step_branding_color(context, color):
    assert context.branding.primary_color == color


@then('the generated CSS defines "{declaration}"')
def step_branding_css(context, declaration):
    assert declaration in context.branding.to_css_variables()

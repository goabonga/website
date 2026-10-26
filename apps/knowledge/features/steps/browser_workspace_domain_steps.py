# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the custom domain settings pages in a browser.

The custom-domain service is the fake of the stack, which records what the pages ask of it
and can be told to refuse. The status it reports for a domain is set in the database, the
way its webhooks would.
"""

from unittest.mock import patch
from uuid import uuid4

import browser_stack
from behave import given, then
from browser_domains import CustomDomains
from playwright.sync_api import expect

from knowledge.models import Organization
from knowledge.models.enums import CustomDomainStatus, PlanType
from knowledge.services.custom_domain import CustomDomainError


@browser_stack.scenario_setup
def install_custom_domains(stack, scenario):
    stack.custom_domains = CustomDomains()
    scenario.enter_context(
        patch(
            "knowledge.routes.web.organizations.get_custom_domain_client",
            lambda: stack.custom_domains,
        )
    )


def _workspace(session, name):
    return session.query(Organization).filter(Organization.name == name).one()


@given(
    'the workspace "{name}" is registered with the domain "{domain}" in the custom-domain service'
)
def step_registered_domain(context, name, domain):
    with context.stack.db.session() as session:
        organization = _workspace(session, name)
        organization.custom_domain = domain
        organization.custom_domain_status = CustomDomainStatus.PENDING
        organization.custom_domain_service_id = "service-existing"
        organization.custom_domain_cname_target = "cname.example.invalid"


@given("the custom-domain service reports the domain of the workspace as active")
def step_active(context):
    with context.stack.db.session() as session:
        organization = (
            session.query(Organization).filter(Organization.custom_domain.is_not(None)).one()
        )
        organization.custom_domain_status = CustomDomainStatus.ACTIVE


@given('the workspace "Other" already uses the domain "{domain}"')
def step_other_workspace(context, domain):
    with context.stack.db.session() as session:
        session.add(
            Organization(
                name="Other",
                slug=f"other-{uuid4().hex[:6]}",
                plan=PlanType.ENTERPRISE,
                custom_domain=domain,
                custom_domain_status=CustomDomainStatus.ACTIVE,
            )
        )


@given("the custom-domain service refuses every registration with {status:d}")
def step_refuses(context, status):
    context.stack.custom_domains.error = CustomDomainError("taken", status_code=status)


@given("the custom-domain service is unavailable")
def step_unavailable(context):
    context.stack.custom_domains.error = CustomDomainError("down", retryable=True)


@then('the custom-domain service registered "{domain}" for the workspace "{name}"')
def step_registered(context, domain, name):
    with context.stack.db.session() as session:
        owner = str(_workspace(session, name).id)
    assert context.stack.custom_domains.registered == [(domain, owner)]


@then("the custom-domain service registered nothing")
def step_nothing_registered(context):
    assert context.stack.custom_domains.registered == []


@then("the custom-domain service verified the domain of the workspace")
def step_verified(context):
    assert context.stack.custom_domains.verified == ["service-existing"]


@then("the custom-domain service deleted the domain of the workspace")
def step_deleted(context):
    assert context.stack.custom_domains.deleted == ["service-existing"]


@then('the page links "{text}" to "{href}"')
def step_links(context, text, href):
    expect(context.page.get_by_role("link", name=text, exact=True)).to_have_attribute("href", href)

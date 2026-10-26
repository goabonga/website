# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the custom domain settings pages.

Routes and templates are real. The Celery tasks that verify and provision a domain
are replaced by recorders; the database is the in-memory store.
"""

from unittest.mock import patch
from uuid import uuid4

from behave import given, then, when

from knowledge.models import Organization
from knowledge.models.enums import CustomDomainStatus, PlanType
from knowledge.services.custom_domain import CustomDomainError, RegisteredDomain


def _patch(context, target, value):
    patcher = patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


class _Service:
    """The custom-domain service, recording what the pages ask of it."""

    def __init__(self):
        self.registered = []
        self.deleted = []
        self.verified = []
        self.error = None

    async def register(self, domain, owner_id):
        if self.error:
            raise self.error
        self.registered.append((domain, owner_id))
        return RegisteredDomain(
            id="svc-1", domain=domain, status="pending", cname_target="apps.example.test"
        )

    async def verify(self, domain_id):
        if self.error:
            raise self.error
        self.verified.append(domain_id)
        return "dns_verifying"

    async def delete(self, domain_id):
        if self.error:
            raise self.error
        self.deleted.append(domain_id)
        return True


@given("the custom-domain service is in memory")
def step_service_in_memory(context):
    context.service = _Service()
    _patch(
        context,
        "knowledge.routes.web.organizations.get_custom_domain_client",
        lambda: context.service,
    )


@given("the custom-domain service refuses registrations with {status:d}")
def step_service_refuses(context, status):
    context.service.error = CustomDomainError("taken", status_code=status)


@given("the custom-domain service is down")
def step_service_down(context):
    context.service.error = CustomDomainError("down", retryable=True)


@given('another workspace already uses the domain "{domain}"')
def step_other_domain(context, domain):
    other = Organization(
        id=uuid4(),
        name="Other",
        slug="other",
        plan=PlanType.ENTERPRISE,
        custom_domain=domain,
        custom_domain_status=CustomDomainStatus.ACTIVE,
    )
    context.store.organizations[other.id] = other


@given('the workspace has the custom domain "{domain}" in status "{status}"')
def step_workspace_domain(context, domain, status):
    context.tenant.custom_domain = domain
    context.tenant.custom_domain_status = CustomDomainStatus(status)


@given(
    'the domain "{domain}" of the workspace is registered in the service as "{domain_id}" in status "{status}"'
)
def step_workspace_registered_domain(context, domain, status, domain_id):
    step_workspace_domain(context, domain, status)
    context.tenant.custom_domain_service_id = domain_id


@when('I set the custom domain to "{domain}"')
def step_set_domain(context, domain):
    context.response = context.call(
        "POST", "/organizations/domain", data={"domain": domain}, follow_redirects=False
    )


@when("I retry the domain verification")
def step_retry(context):
    context.response = context.call("POST", "/organizations/domain/verify", follow_redirects=False)


@when("I remove the custom domain")
def step_remove(context):
    context.response = context.call("POST", "/organizations/domain/remove", follow_redirects=False)


@then('the workspace should have the custom domain "{domain}" in status "{status}"')
def step_has_domain(context, domain, status):
    assert context.tenant.custom_domain == domain
    assert context.tenant.custom_domain_status == CustomDomainStatus(status)


@then('the service should have registered "{domain}" for the workspace')
def step_registered(context, domain):
    assert context.service.registered == [(domain, str(context.tenant.id))], (
        context.service.registered
    )


@then('the workspace should be linked to the service domain with the CNAME target "{target}"')
def step_linked(context, target):
    assert context.tenant.custom_domain_service_id == "svc-1"
    assert context.tenant.custom_domain_cname_target == target


@then('the service should have deleted "{domain_id}"')
def step_deleted(context, domain_id):
    assert context.service.deleted == [domain_id], context.service.deleted


@then('the service should have restarted the verification of "{domain_id}"')
def step_verified(context, domain_id):
    assert context.service.verified == [domain_id], context.service.verified


@then("the service should not have been called")
def step_not_called(context):
    service = context.service
    assert not (service.registered or service.deleted or service.verified)


@then("the workspace should have no custom domain")
def step_no_domain(context):
    assert context.tenant.custom_domain is None
    assert context.tenant.custom_domain_status is None

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the domain API feature."""

from behave import given, then
from custom_domain.models import AuthorizedClient, CustomDomain, DomainStatus
from environment import start_patch
from sqlalchemy import select


def find_domain(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


@given("the verification and provisioning queues are recorded")
def step_queues_recorded(context):
    context.verification = start_patch(context, "custom_domain.tasks.verify_domain_dns")
    context.provisioning = start_patch(context, "custom_domain.tasks.provision_domain_ssl")


@given('the client "{client_id}" may hold {limit:d} domains')
def step_client_limit(context, client_id, limit):
    with context.db.session() as session:
        client = session.scalar(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        )
        client.max_domains = limit
        session.commit()


@given("the deprovisioning queue is recorded")
def step_deprovisioning_recorded(context):
    context.deprovisioning = start_patch(context, "custom_domain.tasks.deprovision_domain")


@given('the client "{client_id}" is deactivated')
def step_client_deactivated(context, client_id):
    with context.db.session() as session:
        client = session.scalar(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        )
        client.is_active = False
        session.commit()


@given('the client "{client_id}" has no default CNAME target')
def step_client_without_cname(context, client_id):
    with context.db.session() as session:
        client = session.scalar(
            select(AuthorizedClient).where(AuthorizedClient.client_id == client_id)
        )
        client.default_cname_target = None
        session.commit()


@given('the default CNAME target setting is "{value}"')
def step_default_cname_setting(context, value):
    start_patch(context, "custom_domain.config.settings.default_cname_target", new=value)


@then('deprovisioning was queued for the domain "{name}"')
def step_deprovisioning_queued(context, name):
    context.deprovisioning.delay.assert_called_once_with(str(find_domain(context, name).id))


@then('DNS verification was queued for the new domain "{name}"')
def step_verification_queued(context, name):
    context.verification.delay.assert_called_once_with(str(find_domain(context, name).id))


@then('SSL provisioning was queued for the domain "{name}"')
def step_provisioning_queued_for(context, name):
    context.provisioning.delay.assert_called_once_with(str(find_domain(context, name).id))


@given('the stored domain "{name}" is active')
def step_stored_domain_active(context, name):
    domain = find_domain(context, name)
    with context.db.session() as session:
        stored = session.get(CustomDomain, domain.id)
        stored.status = DomainStatus.ACTIVE
        session.commit()


@given("no default CNAME target is configured")
def step_no_default_cname(context):
    step_default_cname_setting(context, "")

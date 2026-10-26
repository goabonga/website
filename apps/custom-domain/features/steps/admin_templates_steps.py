# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the nginx template administration feature."""

from unittest.mock import AsyncMock

from behave import given, then
from custom_domain.models import CustomDomain, NginxTemplate
from environment import start_patch
from sqlalchemy import select


def find_template(context, slug):
    with context.db.session() as session:
        return session.scalar(select(NginxTemplate).where(NginxTemplate.slug == slug))


def find_domain(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


@given('a template "{slug}" exists')
def step_template_exists(context, slug):
    with context.db.session() as session:
        template = NginxTemplate(
            slug=slug,
            name=slug.title(),
            http_template="server { server_name {{ domain }}; }",
            https_template="server { listen 443 ssl; server_name {{ domain }}; }",
        )
        session.add(template)
        session.commit()
        context.ids[("template", slug)] = template.id


@given('the template "{slug}" is the default')
def step_template_default(context, slug):
    with context.db.session() as session:
        template = session.scalar(select(NginxTemplate).where(NginxTemplate.slug == slug))
        template.is_default = True
        session.commit()


@given('the domain "{name}" uses the template "{slug}"')
def step_domain_uses_template(context, name, slug):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        domain.nginx_template_id = context.ids[("template", slug)]
        session.commit()


@given("nginx accepts every configuration")
def step_nginx_accepts(context):
    start_patch(
        context,
        "custom_domain.routes.admin.templates.template_service.validate_nginx_syntax_in_worker",
        new=AsyncMock(return_value=(True, "")),
    )


@given("no worker answers the nginx validation")
def step_no_worker(context):
    pending = start_patch(context, "custom_domain.tasks.validation.validate_nginx_template")
    pending.delay.return_value.get.side_effect = TimeoutError("no worker answered")


@given("the provisioning queue is recorded")
def step_queue_recorded(context):
    context.provisioning = start_patch(context, "custom_domain.tasks.provision_domain_ssl")


@then("the first item has the domain count {count:d}")
def step_first_item_count(context, count):
    assert context.response.json()["items"][0]["domains_count"] == count


@then('the template "{slug}" is not the default any more')
def step_not_default(context, slug):
    assert not find_template(context, slug).is_default


@then('the domain "{name}" was queued for SSL provisioning')
def step_queued(context, name):
    domain = find_domain(context, name)
    context.provisioning.delay.assert_called_once_with(str(domain.id))


@then("nothing was queued for provisioning")
def step_nothing_queued(context):
    context.provisioning.delay.assert_not_called()


@given('a template "{slug}" is owned by "{client_id}"')
def step_owned_template_exists(context, slug, client_id):
    with context.db.session() as session:
        template = NginxTemplate(
            slug=slug,
            name=slug.title(),
            client_id=client_id,
            http_template="server { server_name {{ domain }}; }",
            https_template="server { listen 443 ssl; server_name {{ domain }}; }",
        )
        session.add(template)
        session.commit()
        context.ids[("template", slug)] = template.id

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the SSL provisioning feature."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from behave import given, then, when
from celery.exceptions import Retry
from custom_domain.celery import celery_app
from custom_domain.models import CustomDomain, DomainStatus
from custom_domain.services import certbot_service
from custom_domain.services.certbot import CertbotResult
from custom_domain.tasks.provisioning import deprovision_domain, provision_domain_ssl
from environment import start_patch
from sqlalchemy import select


def load_domain(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


@given('a domain "{name}" with the status "{status}" in the database')
def step_domain_in_db(context, name, status):
    with context.db.session() as session:
        session.add(
            CustomDomain(
                domain=name,
                client_id="tenant-a",
                owner_id="org_1",
                owner_type="organization",
                upstream_target="/run/shop.sock",
                cname_target="apps.example.com",
                status=DomainStatus(status),
            )
        )
        session.commit()


def fake_provisioning_environment(context, certbot_result, record_events=True):
    """Replace the database session, nginx, certbot and event publishing of the task.

    With ``record_events=False`` the event publishing is left alone (the webhook
    scenarios route it to the real function themselves).
    """
    start_patch(
        context,
        "custom_domain.tasks.provisioning.get_sync_db",
        side_effect=lambda: context.db.session(),
    )
    if record_events:
        context.events = start_patch(context, "custom_domain.tasks.provisioning.publish_event")
    nginx = start_patch(context, "custom_domain.tasks.provisioning.nginx_manager")
    nginx.generate_http_config = AsyncMock(return_value="http config")
    nginx.generate_https_config = AsyncMock(return_value="https config")
    nginx.write_config = AsyncMock()
    nginx.remove_config = AsyncMock()
    nginx.reload = AsyncMock()
    context.nginx = nginx
    certbot = start_patch(context, "custom_domain.tasks.provisioning.certbot_service")
    certbot.provision_certificate = AsyncMock(return_value=certbot_result)
    certbot.revoke_certificate = AsyncMock(return_value=CertbotResult(success=True))
    context.certbot = certbot


@given("certbot issues a certificate expiring in {days:d} days")
def step_certbot_ok(context, days):
    expires = datetime.now(UTC) + timedelta(days=days)
    fake_provisioning_environment(context, CertbotResult(success=True, expires_at=expires))


@given('certbot fails with "{message}"')
def step_certbot_fails(context, message):
    fake_provisioning_environment(context, CertbotResult(success=False, error_message=message))


@when('the SSL provisioning task runs for "{name}"')
def step_run_provisioning(context, name):
    if not hasattr(context, "nginx"):
        fake_provisioning_environment(context, CertbotResult(success=True))
    domain = load_domain(context, name)
    context.retry_requested = False
    try:
        provision_domain_ssl(domain.id)
    except Retry:
        context.retry_requested = True


@when('the deprovisioning task runs for "{name}"')
def step_run_deprovisioning(context, name):
    fake_provisioning_environment(context, CertbotResult(success=True))
    deprovision_domain(load_domain(context, name).id)


@then('the domain "{name}" has the status "{status}"')
def step_status(context, name, status):
    assert load_domain(context, name).status.value == status


@then('the domain "{name}" has an SSL expiry date')
def step_ssl_expiry(context, name):
    assert load_domain(context, name).ssl_expires_at is not None


@then('the domain "{name}" has the error "{message}"')
def step_error_message(context, name, message):
    assert load_domain(context, name).error_message == message


@then("the nginx configuration was written {writes:d} times and reloaded {reloads:d} times")
def step_nginx_calls(context, writes, reloads):
    assert context.nginx.write_config.await_count == writes
    assert context.nginx.reload.await_count == reloads


@then("no nginx configuration was written")
def step_no_nginx(context):
    assert context.nginx.write_config.await_count == 0


@then("the progress events are")
def step_events(context):
    published = [
        (call.args[1], call.args[2].get("step", "")) for call in context.events.call_args_list
    ]
    expected = [(row["event"], row["step"]) for row in context.table]
    assert published == expected, published


@then('an "{event}" event with the code "{code}" was published')
def step_error_event(context, event, code):
    assert any(
        call.args[1] == event and call.args[2].get("code") == code
        for call in context.events.call_args_list
    ), context.events.call_args_list


@then("the task asks to be retried")
def step_retry(context):
    assert context.retry_requested


@then('the nginx configuration of "{name}" was removed')
def step_removed(context, name):
    context.nginx.remove_config.assert_awaited_once_with(name)
    context.nginx.reload.assert_awaited_once()


@given('certbot is enabled with the e-mail "{email}"')
def step_certbot_enabled(context, email):
    start_patch(context, "custom_domain.config.settings.certbot_enabled", new=True)
    start_patch(context, "custom_domain.config.settings.certbot_email", new=email)


@given("certbot is enabled without an e-mail")
def step_certbot_without_email(context):
    step_certbot_enabled(context, "")


@given("certbot is disabled")
def step_certbot_disabled(context):
    start_patch(context, "custom_domain.config.settings.certbot_enabled", new=False)


@when('I request a certificate for "{name}"')
def step_request_certificate(context, name):
    context.certificate = context.loop.run_until_complete(
        certbot_service.provision_certificate(name)
    )


@then("the certificate request succeeds")
def step_certificate_ok(context):
    assert context.certificate.success


@then('the certificate request fails with "{message}"')
def step_certificate_fails(context, message):
    assert not context.certificate.success
    assert message in context.certificate.error_message, context.certificate.error_message


@then('the certificate of "{name}" was revoked')
def step_revoked(context, name):
    context.certbot.revoke_certificate.assert_awaited_once_with(name)


@then('the domain "{name}" is deleted')
def step_deleted(context, name):
    assert load_domain(context, name).deleted_at is not None


@then('an "{event}" event with the status "{status}" was published')
def step_status_event(context, event, status):
    assert any(
        call.args[1] == event and call.args[2].get("status") == status
        for call in context.events.call_args_list
    ), context.events.call_args_list


@then('the Celery default queue is "{queue}"')
def step_default_queue(context, queue):
    assert celery_app.conf.task_default_queue == queue


@then('the task "{task}" is routed to the queue "{queue}"')
def step_task_route(context, task, queue):
    assert celery_app.amqp.router.route({}, task)["queue"].name == queue


@then("no system command was run")
def step_no_command(context):
    assert context.commands == []


@then('the nginx configuration was rendered from the template "{slug}"')
def step_rendered_from(context, slug):
    template = context.nginx.generate_http_config.call_args.args[1]
    assert template is not None and template.slug == slug, template


@then("the nginx configuration was rendered with the packaged templates")
def step_rendered_packaged(context):
    assert context.nginx.generate_http_config.call_args.args[1] is None

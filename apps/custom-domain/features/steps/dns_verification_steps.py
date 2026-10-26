# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the DNS verification feature."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import dns.resolver
from behave import given, then, when
from celery.exceptions import Retry
from custom_domain.models import CustomDomain
from custom_domain.services import DNSCheckResult, dns_service
from custom_domain.tasks.verification import check_pending_domains, verify_domain_dns
from environment import start_patch
from sqlalchemy import select


def load_domain(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


def fake_resolver(context, resolve):
    resolver = MagicMock()
    resolver.resolve.side_effect = resolve
    start_patch(context, "custom_domain.services.dns.dns_service._resolver", new=resolver)


@given('the domain "{name}" has a CNAME record pointing to "{target}"')
def step_cname_record(context, name, target):
    fake_resolver(context, lambda domain, rtype: [SimpleNamespace(target=target)])


@given('the domain "{name}" does not exist in DNS')
def step_nxdomain(context, name):
    def resolve(domain, rtype):
        raise dns.resolver.NXDOMAIN()

    fake_resolver(context, resolve)


@when('I check the CNAME of "{name}" against "{target}"')
def step_check_cname(context, name, target):
    context.dns_result = context.loop.run_until_complete(dns_service.check_cname(name, target))


@then("the DNS check succeeds")
def step_dns_ok(context):
    assert context.dns_result.success


@then('the DNS check fails with "{message}"')
def step_dns_failed(context, message):
    assert not context.dns_result.success
    assert context.dns_result.error_message == message


def fake_verification_environment(context, result):
    start_patch(
        context,
        "custom_domain.tasks.verification.get_sync_db",
        side_effect=lambda: context.db.session(),
    )
    context.events = start_patch(context, "custom_domain.tasks.verification.publish_event")
    service = start_patch(context, "custom_domain.tasks.verification.dns_service")
    service.check_cname = AsyncMock(return_value=result)
    context.provisioning = start_patch(
        context, "custom_domain.tasks.provisioning.provision_domain_ssl"
    )


@given("the DNS check of the task succeeds")
def step_task_dns_ok(context):
    fake_verification_environment(
        context, DNSCheckResult(success=True, actual_value="apps.example.com", expected_value="x")
    )


@given('the DNS check of the task fails with "{message}"')
def step_task_dns_fails(context, message):
    fake_verification_environment(
        context,
        DNSCheckResult(success=False, actual_value=None, expected_value="x", error_message=message),
    )


@given("the task may not be retried")
def step_no_retry(context):
    start_patch(context, "custom_domain.tasks.verification.verify_domain_dns.max_retries", new=0)


@when('the DNS verification task runs for "{name}"')
def step_run_verification(context, name):
    domain = load_domain(context, name)
    context.retry_requested = False
    try:
        verify_domain_dns(domain.id)
    except Retry:
        context.retry_requested = True


@then('SSL provisioning was queued for "{name}"')
def step_provisioning_queued(context, name):
    domain = load_domain(context, name)
    context.provisioning.delay.assert_called_once_with(domain.id)


@then('the domain "{name}" has {count:d} failed verification')
def step_failed_count(context, name, count):
    assert load_domain(context, name).retry_count == count


@given('the domain "{name}" was checked {minutes:d} minutes ago')
def step_checked_ago(context, name, minutes):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        domain.last_check_at = datetime.now(UTC) - timedelta(minutes=minutes)
        session.commit()


@when("the periodic pending domains check runs")
def step_periodic_check(context):
    start_patch(
        context,
        "custom_domain.tasks.verification.get_sync_db",
        side_effect=lambda: context.db.session(),
    )
    context.verify_task = start_patch(context, "custom_domain.tasks.verification.verify_domain_dns")
    check_pending_domains()


@then('DNS verification was queued for "{name}" only')
def step_only_queued(context, name):
    queued = [call.args[0] for call in context.verify_task.delay.call_args_list]
    assert queued == [str(load_domain(context, name).id)], queued


@then('the beat schedule runs "{task}"')
def step_beat(context, task):
    from custom_domain.celery import celery_app

    assert task in {entry["task"] for entry in celery_app.conf.beat_schedule.values()}


@then('the beat entry "{name}" is published to the queue "{queue}"')
def step_beat_queue(context, name, queue):
    from custom_domain.celery import celery_app

    assert celery_app.conf.beat_schedule[name]["options"] == {"queue": queue}

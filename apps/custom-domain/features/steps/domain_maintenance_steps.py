# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the domain maintenance feature."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from behave import given, then, when
from custom_domain.models import CustomDomain
from custom_domain.services.certbot import CertificateInfo
from custom_domain.services.dns import DNSCheckResult
from custom_domain.tasks import maintenance
from environment import start_patch
from sqlalchemy import select


def load(context, name):
    with context.db.session() as session:
        return session.scalar(select(CustomDomain).where(CustomDomain.domain == name))


def update(context, name, **values):
    with context.db.session() as session:
        domain = session.scalar(select(CustomDomain).where(CustomDomain.domain == name))
        for key, value in values.items():
            setattr(domain, key, value)
        session.commit()


@given("the maintenance tasks use the fake database and record the task queue")
def step_fake_environment(context):
    start_patch(
        context,
        "custom_domain.tasks.maintenance.get_sync_db",
        side_effect=lambda: context.db.session(),
    )
    context.provisioning = start_patch(
        context, "custom_domain.tasks.maintenance.provision_domain_ssl"
    )
    context.deprovisioning = start_patch(
        context, "custom_domain.tasks.maintenance.deprovision_domain"
    )
    context.certbot = start_patch(context, "custom_domain.tasks.maintenance.certbot_service")
    context.dns = start_patch(context, "custom_domain.tasks.maintenance.dns_service")


@given('the certificate of "{name}" expires in {days:d} days')
def step_certificate_expiry(context, name, days):
    update(context, name, ssl_expires_at=datetime.now(UTC) + timedelta(days=days))


@given("certbot reports {days:d} days left")
def step_certbot_days(context, days):
    context.certbot.check_certificate = AsyncMock(
        return_value=CertificateInfo(
            domain="x", issued_at=None, expires_at=datetime.now(UTC), days_until_expiry=days
        )
    )


@given("DNS answers correctly")
def step_dns_ok(context):
    context.dns.check_cname = AsyncMock(
        return_value=DNSCheckResult(success=True, actual_value="a", expected_value="a")
    )


@given('DNS fails with "{message}"')
def step_dns_fails(context, message):
    context.dns.check_cname = AsyncMock(
        return_value=DNSCheckResult(
            success=False, actual_value=None, expected_value="a", error_message=message
        )
    )


@given('the domain "{name}" was created {days:d} days ago')
def step_created_ago(context, name, days):
    update(context, name, created_at=datetime.now(UTC) - timedelta(days=days))


@given('the domain "{name}" was soft-deleted {days:d} days ago')
def step_deleted_ago(context, name, days):
    update(context, name, deleted_at=datetime.now(UTC) - timedelta(days=days))


@when("the certificate expiry check runs")
def step_run_expiry(context):
    maintenance.check_certificate_expiry()


@when("the domain health check runs")
def step_run_health(context):
    maintenance.check_domain_health()


@when("the stale domain cleanup runs")
def step_run_cleanup(context):
    maintenance.cleanup_stale_domains()


@when("the purge of deleted domains runs")
def step_run_purge(context):
    maintenance.purge_deleted_domains()


@then('SSL provisioning was requested for "{name}"')
def step_provisioning_requested(context, name):
    context.provisioning.delay.assert_called_once_with(str(load(context, name).id))


@then("no SSL provisioning was requested")
def step_no_provisioning(context):
    context.provisioning.delay.assert_not_called()


@then('the domain "{name}" was queued for deprovisioning without revoking its certificate')
def step_deprovisioning_queued(context, name):
    context.deprovisioning.delay.assert_called_once_with(str(load(context, name).id), False)


@then('the domain "{name}" is soft-deleted')
def step_soft_deleted(context, name):
    assert load(context, name).deleted_at is not None


@then('the domain "{name}" is not soft-deleted')
def step_not_soft_deleted(context, name):
    assert load(context, name).deleted_at is None


@then('the domain "{name}" no longer exists')
def step_gone(context, name):
    assert load(context, name) is None


@then('the domain "{name}" still exists')
def step_exists(context, name):
    assert load(context, name) is not None


@then('the beat entry "{name}" runs at hour {hour:d} on day of week {day:d}')
def step_beat_time(context, name, hour, day):
    from custom_domain.celery import celery_app

    schedule = celery_app.conf.beat_schedule[name]["schedule"]
    assert schedule.hour == {hour}
    assert schedule.day_of_week == {day}

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for admin.feature, on the in-memory database."""

import uuid
from datetime import UTC, datetime, timedelta

from behave import given, then
from vpn_portal.db.models import VPNCertificate, VPNConnection


def _add_certificate(context, **overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "username": "test@example.com",
        "serial_number": f"serial-{uuid.uuid4().hex[:12]}",
        "common_name": f"vpn-{uuid.uuid4().hex[:12]}",
        "not_before": now - timedelta(minutes=5),
        "not_after": now + timedelta(minutes=10),
        "scopes": ["vpn:connect"],
        "assigned_routes": ["10.8.0.0/24"],
    }
    certificate = VPNCertificate(**(values | overrides))
    context.db.add(certificate)
    context.run(context.db.commit())
    return certificate


@given("the database contains {count:d} active sessions")
def step_db_has_sessions(context, count):
    for index in range(count):
        certificate = _add_certificate(
            context,
            username=f"user{index}@example.com",
            device_name=f"device-{index}",
            created_at=datetime.now(UTC) - timedelta(minutes=index),
        )
        context.db.add(
            VPNConnection(
                id=uuid.uuid4(),
                certificate_id=certificate.id,
                connected_at=datetime.now(UTC) - timedelta(minutes=1),
                assigned_ip=f"10.8.0.{index + 2}",
                client_ip=f"203.0.113.{index + 10}",
            )
        )
    context.run(context.db.commit())


@given('a certificate with serial "{serial}" exists')
def step_cert_with_serial_exists(context, serial):
    context.certificate = _add_certificate(context, serial_number=serial)


@given('no certificate with serial "{serial}" exists')
def step_no_cert_with_serial(context, serial):
    assert all(c.serial_number != serial for c in context.db.rows("vpn_certificates"))


@then('the first session should have the assigned IP "{ip}"')
def step_first_session_ip(context, ip):
    assert context.response.json()["sessions"][0]["assigned_ip"] == ip


@then('the certificate "{serial}" should be revoked with reason "{reason}"')
def step_revoked_with_reason(context, serial, reason):
    certificate = next(c for c in context.db.rows("vpn_certificates") if c.serial_number == serial)
    assert certificate.is_revoked
    assert certificate.revocation_reason == reason


@then('the certificate authority should have revoked "{serial}"')
def step_ca_revoked_serial(context, serial):
    context.stepca.revoke_certificate.assert_awaited_once_with(serial)

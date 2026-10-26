# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Step definitions for internal.feature (OpenVPN hook API), on the in-memory database."""

import uuid
from datetime import UTC, datetime, timedelta

from behave import given, then
from vpn_portal.db.models import VPNCertificate, VPNConnection


def _add_certificate(context, common_name, **overrides):
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "username": "user@example.com",
        "serial_number": f"serial-{uuid.uuid4().hex[:12]}",
        "common_name": common_name,
        "not_before": now - timedelta(minutes=5),
        "not_after": now + timedelta(minutes=10),
        "scopes": ["vpn:connect"],
        "assigned_routes": ["10.8.0.0/24", "10.0.0.0/8"],
    }
    certificate = VPNCertificate(**(values | overrides))
    context.db.add(certificate)
    context.run(context.db.commit())
    return certificate


def _connections(context, common_name):
    certificate = next(
        c for c in context.db.rows("vpn_certificates") if c.common_name == common_name
    )
    return [c for c in context.db.rows("vpn_connections") if c.certificate_id == certificate.id]


@given('a certificate with common name "{cn}" is valid')
def step_cert_is_valid(context, cn):
    _add_certificate(context, cn)


@given('a certificate with common name "{cn}" exists in the database')
def step_cert_exists(context, cn):
    _add_certificate(context, cn)


@given('no certificate with common name "{cn}" exists')
def step_no_cert(context, cn):
    assert all(c.common_name != cn for c in context.db.rows("vpn_certificates"))


@given('a certificate with common name "{cn}" is revoked')
def step_cert_is_revoked(context, cn):
    _add_certificate(context, cn, revoked_at=datetime.now(UTC), revocation_reason="test_revocation")


@given('a certificate with common name "{cn}" is expired')
def step_cert_is_expired(context, cn):
    now = datetime.now(UTC)
    _add_certificate(
        context, cn, not_before=now - timedelta(minutes=20), not_after=now - timedelta(minutes=1)
    )


@given('a connection for common name "{cn}" is active')
def step_connection_is_active(context, cn):
    certificate = _add_certificate(context, cn)
    context.db.add(
        VPNConnection(
            id=uuid.uuid4(),
            certificate_id=certificate.id,
            connected_at=datetime.now(UTC) - timedelta(minutes=2),
            assigned_ip="10.8.0.5",
            client_ip="203.0.113.1",
        )
    )
    context.run(context.db.commit())


@given('no active connection for common name "{cn}" exists')
def step_no_active_connection(context, cn):
    _add_certificate(context, cn)


@then('an active connection should be recorded for "{cn}" from "{assigned_ip}"')
def step_connection_recorded(context, cn, assigned_ip):
    (connection,) = _connections(context, cn)
    assert connection.is_active
    assert connection.assigned_ip == assigned_ip


@then('the connection of "{cn}" should be closed with {rx:d} bytes received and {tx:d} bytes sent')
def step_connection_closed(context, cn, rx, tx):
    (connection,) = _connections(context, cn)
    assert not connection.is_active
    assert (connection.bytes_received, connection.bytes_sent) == (rx, tx)


@then("no connection should be recorded")
def step_no_connection(context):
    assert context.db.rows("vpn_connections") == []

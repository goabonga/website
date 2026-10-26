# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the VPNConnection model."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, ForeignKey
from vpn_portal.db.base import Base
from vpn_portal.db.models import VPNCertificate, VPNConnection


def make_connection(**overrides) -> VPNConnection:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "certificate_id": uuid.uuid4(),
        "connected_at": now - timedelta(seconds=90),
        "assigned_ip": "10.8.0.2",
        "client_ip": "203.0.113.7",
    }
    return VPNConnection(**(values | overrides))


class TestTable:
    table = VPNConnection.__table__

    def test_is_registered_in_the_metadata(self):
        assert Base.metadata.tables["vpn_connections"] is self.table

    def test_columns(self):
        assert list(self.table.c.keys()) == [
            "id",
            "certificate_id",
            "connected_at",
            "disconnected_at",
            "assigned_ip",
            "client_ip",
            "bytes_received",
            "bytes_sent",
            "created_at",
            "updated_at",
        ]

    def test_certificate_foreign_key_cascades(self):
        (foreign_key,) = self.table.c.certificate_id.foreign_keys

        assert isinstance(foreign_key.constraint.elements[0], ForeignKey)
        assert foreign_key.target_fullname == "vpn_certificates.id"
        assert foreign_key.ondelete == "CASCADE"
        assert self.table.c.certificate_id.index is True

    def test_traffic_counters_are_big_integers(self):
        for name in ("bytes_received", "bytes_sent"):
            assert isinstance(self.table.c[name].type, BigInteger)

    def test_ip_columns_fit_ipv6(self):
        assert self.table.c.assigned_ip.type.length == 45
        assert self.table.c.client_ip.type.length == 45

    def test_disconnected_at_is_optional(self):
        assert self.table.c.disconnected_at.nullable is True
        assert self.table.c.connected_at.nullable is False


class TestBehaviour:
    def test_open_connection_is_active(self):
        connection = make_connection()

        assert connection.is_active
        assert connection.duration_seconds is None

    def test_closed_connection_has_a_duration(self):
        connected_at = datetime.now(UTC) - timedelta(minutes=2)
        connection = make_connection(
            connected_at=connected_at, disconnected_at=connected_at + timedelta(seconds=75)
        )

        assert not connection.is_active
        assert connection.duration_seconds == 75


def test_certificate_connection_relationship():
    certificate_relationship = VPNCertificate.connections.property
    connection_relationship = VPNConnection.certificate.property

    assert certificate_relationship.back_populates == "certificate"
    assert connection_relationship.back_populates == "connections"
    assert "delete-orphan" in certificate_relationship.cascade

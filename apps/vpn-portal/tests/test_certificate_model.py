# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for the VPNCertificate model."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import ARRAY
from vpn_portal.db.base import Base
from vpn_portal.db.models import VPNCertificate


def make_certificate(**overrides) -> VPNCertificate:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "username": "user@example.com",
        "serial_number": "abc123",
        "common_name": "vpn-user-1",
        "not_before": now - timedelta(minutes=1),
        "not_after": now + timedelta(minutes=10),
        "scopes": ["vpn:connect"],
        "assigned_routes": ["10.8.0.0/24"],
    }
    return VPNCertificate(**(values | overrides))


class TestTable:
    table = VPNCertificate.__table__

    def test_is_registered_in_the_metadata(self):
        assert Base.metadata.tables["vpn_certificates"] is self.table

    def test_columns(self):
        assert list(self.table.c.keys()) == [
            "id",
            "user_id",
            "username",
            "serial_number",
            "common_name",
            "not_before",
            "not_after",
            "device_name",
            "scopes",
            "assigned_routes",
            "revoked_at",
            "revocation_reason",
            "created_at",
            "updated_at",
        ]

    def test_required_and_optional_columns(self):
        required = {c.name for c in self.table.c if not c.nullable}
        assert {"user_id", "username", "serial_number", "common_name", "not_after"} <= required
        optional = {c.name for c in self.table.c if c.nullable}
        assert optional == {"device_name", "revoked_at", "revocation_reason"}

    def test_serial_number_is_unique(self):
        assert self.table.c.serial_number.unique is True
        assert self.table.c.serial_number.type.length == 64

    def test_array_columns(self):
        for name in ("scopes", "assigned_routes"):
            column_type = self.table.c[name].type
            assert isinstance(column_type, ARRAY)
            assert isinstance(column_type.item_type, String)

    def test_timestamps_are_timezone_aware(self):
        for name in ("not_before", "not_after", "revoked_at"):
            column_type = self.table.c[name].type
            assert isinstance(column_type, DateTime)
            assert column_type.timezone is True

    def test_indexed_columns(self):
        indexed = {c.name for c in self.table.c if c.index}
        assert indexed == {"user_id", "serial_number", "common_name", "not_after", "revoked_at"}


class TestLifecycle:
    def test_fresh_certificate_is_valid(self):
        certificate = make_certificate()

        assert not certificate.is_revoked
        assert not certificate.is_expired
        assert certificate.is_valid

    def test_revoked_certificate_is_not_valid(self):
        certificate = make_certificate(revoked_at=datetime.now(UTC), revocation_reason="admin")

        assert certificate.is_revoked
        assert not certificate.is_expired
        assert not certificate.is_valid

    def test_expired_certificate_is_not_valid(self):
        certificate = make_certificate(not_after=datetime.now(UTC) - timedelta(seconds=1))

        assert certificate.is_expired
        assert not certificate.is_revoked
        assert not certificate.is_valid

    def test_expired_and_revoked(self):
        certificate = make_certificate(
            not_after=datetime.now(UTC) - timedelta(minutes=5), revoked_at=datetime.now(UTC)
        )

        assert certificate.is_expired
        assert certificate.is_revoked
        assert not certificate.is_valid

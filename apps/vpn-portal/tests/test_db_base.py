# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for vpn_portal.db.base."""

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from vpn_portal.db.base import Base, TimestampMixin, convention


def test_naming_convention_is_applied_to_metadata():
    assert Base.metadata.naming_convention == convention
    assert set(convention) == {"ix", "uq", "ck", "fk", "pk"}


def test_timestamp_mixin_adds_server_side_timestamps():
    class Sample(Base, TimestampMixin):
        __tablename__ = "sample_for_mixin_test"

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        name: Mapped[str] = mapped_column(String(10))

    try:
        for name in ("created_at", "updated_at"):
            column = Sample.__table__.c[name]
            assert isinstance(column.type, DateTime)
            assert column.type.timezone is True
            assert column.nullable is False
            assert column.server_default is not None
        assert Sample.__table__.c.updated_at.onupdate is not None
        assert Sample.__table__.c.created_at.onupdate is None
    finally:
        Base.metadata.remove(Sample.__table__)

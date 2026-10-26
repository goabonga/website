# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Sanity tests of the in-memory session used by the other tests."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fake_session import FakeSession
from sqlalchemy import func, select
from vpn_portal.db.models import VPNCertificate


def certificate(serial: str, minutes_left: int = 10, **overrides) -> VPNCertificate:
    now = datetime.now(UTC)
    values = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "username": "u",
        "serial_number": serial,
        "common_name": f"cn-{serial}",
        "not_before": now,
        "not_after": now + timedelta(minutes=minutes_left),
        "scopes": [],
        "assigned_routes": [],
    }
    return VPNCertificate(**(values | overrides))


@pytest.fixture
async def session():
    db = FakeSession()
    for serial, minutes in (("a", 10), ("b", 20), ("c", -5)):
        db.add(certificate(serial, minutes))
    await db.commit()
    return db


async def test_commit_stores_rows_and_sets_timestamps(session):
    rows = session.rows("vpn_certificates")

    assert [row.serial_number for row in rows] == ["a", "b", "c"]
    assert all(row.created_at is not None for row in rows)


async def test_equality_filter(session):
    result = await session.execute(
        select(VPNCertificate).where(VPNCertificate.serial_number == "b")
    )

    assert result.scalar_one_or_none().serial_number == "b"


async def test_unknown_row_is_none(session):
    result = await session.execute(
        select(VPNCertificate).where(VPNCertificate.serial_number == "zzz")
    )

    assert result.scalar_one_or_none() is None


async def test_is_null_and_greater_than(session):
    now = datetime.now(UTC)
    result = await session.execute(
        select(VPNCertificate)
        .where(VPNCertificate.revoked_at.is_(None))
        .where(VPNCertificate.not_after > now)
    )

    assert {row.serial_number for row in result.scalars().all()} == {"a", "b"}


async def test_order_limit_offset(session):
    query = select(VPNCertificate).order_by(VPNCertificate.not_after.desc())

    assert [r.serial_number for r in (await session.execute(query)).scalars().all()] == [
        "b",
        "a",
        "c",
    ]
    page = await session.execute(query.offset(1).limit(1))
    assert [r.serial_number for r in page.scalars().all()] == ["a"]


async def test_count(session):
    result = await session.execute(select(func.count(VPNCertificate.id)))

    assert result.scalar() == 3


async def test_first_on_empty_result(session):
    result = await session.execute(select(VPNCertificate).where(VPNCertificate.username == "x"))

    assert result.scalars().first() is None


async def test_close_is_recorded(session):
    await session.close()

    assert session.closed

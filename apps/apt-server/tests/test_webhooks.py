# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Signed webhooks sent by the auth service."""

import hashlib
import hmac
import json
import time

import pytest
from apt_server.config import settings
from apt_server.db.models import ACLRole, Package, PackageACL, UserCache
from apt_server.routes.webhooks import _verify_signature
from sqlalchemy import select

SECRET = "whsec"


def sign(body: bytes, secret: str = SECRET, timestamp: int | None = None) -> str:
    ts = str(int(time.time()) if timestamp is None else timestamp)
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


@pytest.fixture(autouse=True)
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "webhook_secret", SECRET)


async def send(http, event: str, data: dict, signature: str | None = None):
    body = json.dumps({"event": event, "data": data}).encode()
    return await http.post(
        "/webhooks/auth",
        content=body,
        headers={
            "X-Webhook-Signature": signature or sign(body),
            "X-Webhook-Event": event,
            "Content-Type": "application/json",
        },
    )


def test_valid_signature_is_accepted() -> None:
    assert _verify_signature(b"{}", sign(b"{}"))


def test_signature_with_wrong_secret_is_rejected() -> None:
    assert not _verify_signature(b"{}", sign(b"{}", secret="other"))


def test_signature_of_another_body_is_rejected() -> None:
    assert not _verify_signature(b'{"a":1}', sign(b"{}"))


def test_old_signatures_are_rejected() -> None:
    assert not _verify_signature(b"{}", sign(b"{}", timestamp=int(time.time()) - 301))


@pytest.mark.parametrize("header", ["", "garbage", "t=abc,v1=ff", "t=1", "v1=ff"])
def test_malformed_signatures_are_rejected(header) -> None:
    assert not _verify_signature(b"{}", header)


def test_signature_check_is_skipped_without_a_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "webhook_secret", "")

    assert _verify_signature(b"{}", "whatever")


async def test_invalid_signature_is_unauthorized(http) -> None:
    response = await send(http, "user.created", {}, signature="t=1,v1=bad")

    assert response.status_code == 401


async def test_headers_are_required(http) -> None:
    assert (await http.post("/webhooks/auth", content=b"{}")).status_code == 422


@pytest.mark.parametrize(
    "event", ["user.created", "user.updated", "user.email_changed", "user.email_verified"]
)
async def test_user_events_fill_the_cache(http, db, event) -> None:
    response = await send(
        http,
        event,
        {"user_id": "s1", "email": "a@example.com", "name": "Alice", "picture": "/a.png"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    row = await db.get(UserCache, "s1")
    assert (row.email, row.name, row.avatar_url) == ("a@example.com", "Alice", "/a.png")


async def test_alternative_payload_field_names(http, db) -> None:
    await send(
        http,
        "user.updated",
        {"id": "s1", "new_email": "n@example.com", "display_name": "N", "avatar_url": "/n.png"},
    )

    row = await db.get(UserCache, "s1")
    assert (row.email, row.name, row.avatar_url) == ("n@example.com", "N", "/n.png")


async def test_events_without_identity_are_ignored(http, db) -> None:
    await send(http, "user.created", {"email": "a@example.com"})
    await send(http, "user.created", {"user_id": "s1"})

    assert (await db.execute(select(UserCache))).scalars().all() == []


async def test_email_change_rewrites_acl_grants(http, db) -> None:
    package = Package(
        name="demo", version="1", architecture="amd64", suite="stable", component="main",
        owner_id="alice", filename="pool/x.deb", size=1, md5="0" * 32, sha1="1" * 40,
        sha256="2" * 64,
    )  # fmt: skip
    package.acl.append(
        PackageACL(grantee_user_id="old@example.com", role=ACLRole.READ, granted_by="alice")
    )
    db.add(package)
    await db.commit()

    await send(
        http,
        "user.email_changed",
        {"user_id": "s1", "email": "new@example.com", "old_email": "old@example.com"},
    )

    db.expire_all()
    grantee = (await db.execute(select(PackageACL.grantee_user_id))).scalar_one()
    assert grantee == "new@example.com"


async def test_deleted_users_are_removed_from_the_cache(http, db) -> None:
    db.add(UserCache(sub="s1", email="a@example.com"))
    await db.commit()

    response = await send(http, "user.deleted", {"user_id": "s1"})

    assert response.status_code == 200
    db.expire_all()
    assert await db.get(UserCache, "s1") is None


async def test_unknown_events_are_acknowledged(http) -> None:
    assert (await send(http, "org.created", {})).status_code == 200

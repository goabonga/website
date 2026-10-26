# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the user cache and webhooks feature."""

import hashlib
import hmac
import json
import time

from apt_server.config import settings
from apt_server.db.models import ACLRole, Package, PackageACL, UserCache
from apt_server.services import user_cache
from behave import given, then, when
from sqlalchemy import select


@given('the webhook secret is "{secret}"')
def set_secret(context, secret):
    context.webhook_secret = secret
    context.patch(settings, "webhook_secret", secret)


def post_event(context, event, data, secret=None):
    body = json.dumps({"event": event, "data": data}).encode()
    timestamp = str(int(time.time()))
    key = (secret or context.webhook_secret).encode()
    digest = hmac.new(key, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    context.response = context.client.post(
        "/webhooks/auth",
        content=body,
        headers={
            "X-Webhook-Signature": f"t={timestamp},v1={digest}",
            "X-Webhook-Event": event,
            "Content-Type": "application/json",
        },
    )


@when('the auth service sends a signed "{event}" event for user "{sub}" with email "{email}"')
def signed_event(context, event, sub, email):
    post_event(context, event, {"user_id": sub, "email": email})


@when(
    'the auth service reports "{event}" for user "{sub}" changing email from "{old}" to "{email}"'
)
def signed_event_with_old_email(context, event, sub, old, email):
    post_event(context, event, {"user_id": sub, "email": email, "old_email": old})


@when("the auth service sends an event signed with the wrong secret")
def wrongly_signed_event(context):
    post_event(context, "user.created", {"user_id": "u-1", "email": "x@example.com"}, secret="nope")


@given('the user "{sub}" is cached with email "{email}"')
def cache_user(context, sub, email):
    async def store(session):
        await user_cache.upsert(session, sub=sub, email=email)

    context.run_db(store)


@then('the user "{sub}" is cached with email "{email}"')
def user_is_cached(context, sub, email):
    async def read(session):
        row = await session.get(UserCache, sub)
        return row.email if row else None

    assert context.run_db(read) == email


@then('the user "{sub}" is not cached')
def user_not_cached(context, sub):
    async def read(session):
        return await session.get(UserCache, sub)

    assert context.run_db(read) is None


@given('a package "{name}" owned by "{owner}" is shared with "{grantee}"')
def shared_package(context, name, owner, grantee):
    async def seed(session):
        package = Package(
            name=name,
            version="1.0",
            architecture="amd64",
            suite="stable",
            component="main",
            owner_id=owner,
            filename=f"pool/main/{name[0]}/{name}/{name}_1.0_amd64.deb",
            size=1,
            md5="0" * 32,
            sha1="1" * 40,
            sha256="2" * 64,
        )
        package.acl.append(PackageACL(grantee_user_id=grantee, role=ACLRole.READ, granted_by=owner))
        session.add(package)
        await session.commit()

    context.run_db(seed)


@then('the package "{name}" is shared with "{grantee}"')
def package_shared_with(context, name, grantee):
    async def read(session):
        rows = await session.execute(
            select(PackageACL.grantee_user_id).join(Package).where(Package.name == name)
        )
        return list(rows.scalars())

    assert context.run_db(read) == [grantee]


@then('the identifier "{identifier}" is displayed as "{display}"')
def displayed_as(context, identifier, display):
    async def resolve(session):
        return await user_cache.resolve_display(session, identifier)

    assert context.run_db(resolve) == display

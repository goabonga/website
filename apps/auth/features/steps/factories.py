# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Helpers that insert rows directly into the scenario database."""

import uuid

from auth.core.security import hash_password
from auth.db.models.tenant import (
    CustomDomainStatus,
    Tenant,
    TenantTrustMode,
    TenantWebhook,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from auth.db.models.user import User, UserEmail, UserPassword

DEFAULT_PASSWORD = "Passw0rd!x"


def make_tenant(
    session,
    slug,
    *,
    platform=False,
    custom_domain=None,
    trust_mode=TenantTrustMode.NONE,
    active=True,
):
    """Insert a tenant; a custom domain is created in the ``active`` state."""
    tenant = Tenant(
        slug=slug,
        display_name=slug.title(),
        is_platform=platform,
        is_active=active,
        custom_domain=custom_domain,
        custom_domain_status=CustomDomainStatus.ACTIVE if custom_domain else None,
        trust_mode=trust_mode,
        settings={},
    )
    session.add(tenant)
    session.flush()
    return tenant


def make_user(
    session,
    email="user@example.com",
    password=DEFAULT_PASSWORD,
    *,
    verified=True,
    registration_tenant_id=None,
):
    """Insert a user with a primary e-mail address and a current password."""
    user = User(is_active=True, registration_tenant_id=registration_tenant_id)
    session.add(user)
    session.flush()
    session.add(UserEmail(user_id=user.id, email=email, is_primary=True, is_verified=verified))
    session.add(
        UserPassword(user_id=user.id, password_hash=hash_password(password), is_current=True)
    )
    session.flush()
    return user


def new_id():
    return uuid.uuid4()


def make_webhook(session, tenant, url, events, *, name="hook", secret="whsec"):
    """Insert an active webhook subscription for ``tenant``."""
    webhook = TenantWebhook(
        tenant_id=tenant.id, name=name, url=url, events=events, secret=secret, headers={}
    )
    session.add(webhook)
    session.flush()
    return webhook


def make_delivery(session, webhook, *, event="user.created", max_attempts=5):
    """Insert a pending delivery for ``webhook``."""
    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        tenant_id=webhook.tenant_id,
        event=event,
        idempotency_key=uuid.uuid4().hex,
        request_url=webhook.url,
        request_headers={},
        request_body={"event": event, "data": {}},
        status=WebhookDeliveryStatus.PENDING,
        attempt=0,
        max_attempts=max_attempts,
    )
    session.add(delivery)
    session.flush()
    return delivery

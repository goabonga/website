# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Steps for the custom domains feature.

The custom-domain service is an httpx mock transport and the OAuth2 server a fake token
cache. The webhook receiver and the reconciliation task run for real over a fake
database session that serves one organization, and the delivery ids live in a set instead
of Redis.
"""

import asyncio
import hashlib
import hmac
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
from behave import given, then, when

from knowledge.config import get_settings
from knowledge.models import Organization
from knowledge.models.enums import CustomDomainStatus, PlanType
from knowledge.routes import custom_domain_webhooks as webhooks
from knowledge.services import custom_domain as service
from knowledge.services.custom_domain import CustomDomainClient, CustomDomainError
from knowledge.tasks import custom_domain as tasks

SECRET = "s3cret-of-at-least-thirty-two-characters"


def _patch(context, target, value, attribute=False):
    patcher = patch.object(*target, value) if attribute else patch(target, value)
    patcher.start()
    context.add_cleanup(patcher.stop)


# --- validation and statuses ------------------------------------------------


@then('the domain "{domain}" should be {verdict}')
def step_validate(context, domain, verdict):
    valid, _ = service.validate_domain(domain)
    assert valid == (verdict == "accepted"), (domain, valid)


@then('the status "{status}" of the service should be recorded as "{recorded}"')
def step_map_status(context, status, recorded):
    mapped = service.map_status(status)
    expected = None if recorded == "not recorded" else CustomDomainStatus(recorded)
    assert mapped == expected, (status, mapped)


# --- the client of the service ------------------------------------------------


class _Tokens:
    def get(self, credentials, scope):
        return "tok"

    async def aget(self, credentials, scope):
        return "tok"

    def clear(self):
        pass


def _client(context, handler, configured=True):
    settings = MagicMock(
        custom_domain_service_url="http://domains.test" if configured else "",
        custom_domain_service_socket_path="",
        service_timeout=5.0,
    )
    with patch.object(service, "get_settings", return_value=settings):
        client = CustomDomainClient()
    client._tokens = _Tokens()
    context.service_requests = []

    def recording(request):
        context.service_requests.append(request)
        return handler(request)

    real = httpx.AsyncClient
    client._http_client = lambda: real(transport=httpx.MockTransport(recording))
    context.service = client
    context.error = None
    context.registered = None


@given('the custom-domain service accepts registrations with the CNAME target "{target}"')
def step_accepts(context, target):
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "id": "svc-1",
                "domain": body["domain"],
                "status": "pending",
                "cname_target": target,
                "owner_id": body["owner_id"],
                "owner_type": "organization",
                "dns_instructions": f"Create a CNAME record to {target}",
            },
        )

    _client(context, handler)


@given('the custom-domain service answers {status:d} "{detail}"')
def step_answers(context, status, detail):
    _client(context, lambda request: httpx.Response(status, json={"detail": detail}))


@given("no custom-domain service is configured")
def step_unconfigured(context):
    _client(context, lambda request: httpx.Response(500), configured=False)


@given("the custom-domain service restarts verifications")
def step_restarts(context):
    _client(
        context,
        lambda request: httpx.Response(
            200, json={"id": "svc-1", "status": "dns_verifying", "message": "restarted"}
        ),
    )


@given("the custom-domain service removes domains")
def step_removes(context):
    _client(context, lambda request: httpx.Response(202, json={"id": "svc-1"}))


@given("the custom-domain service does not know the domain")
def step_forgot(context):
    _client(context, lambda request: httpx.Response(404, json={"detail": "Domain not found"}))


@when('the workspace "{slug}" registers the domain "{domain}"')
def step_register(context, slug, domain):
    context.registered = asyncio.run(context.service.register(domain, slug))


@when('the workspace "{slug}" tries to register the domain "{domain}"')
def step_try_register(context, slug, domain):
    try:
        asyncio.run(context.service.register(domain, slug))
    except CustomDomainError as error:
        context.error = error


@when('the verification of the domain "{domain_id}" is restarted')
def step_verify(context, domain_id):
    context.new_status = asyncio.run(context.service.verify(domain_id))


@when('the domain "{domain_id}" is deleted')
def step_delete(context, domain_id):
    context.deleted = asyncio.run(context.service.delete(domain_id))


@then('the service should have been asked to register "{domain}" for the workspace "{slug}"')
def step_asked_register(context, domain, slug):
    request = context.service_requests[-1]
    assert request.method == "POST" and request.url.path == "/api/v1/domains"
    assert request.headers["authorization"] == "Bearer tok"
    body = json.loads(request.content)
    assert (body["domain"], body["owner_id"], body["owner_type"]) == (
        domain,
        slug,
        "organization",
    )


@then("the request should not name an upstream, a CNAME target or a certificate")
def step_no_infrastructure(context):
    body = json.loads(context.service_requests[-1].content)
    assert not {"upstream_target", "cname_target", "nginx_template_id"} & set(body), body


@then('the registration should return the CNAME target "{target}"')
def step_cname(context, target):
    assert context.registered.cname_target == target
    assert context.registered.id == "svc-1"


@then('the registration should be refused with {status:d} "{detail}"')
def step_refused(context, status, detail):
    assert context.error is not None and context.error.status_code == status, context.error
    assert context.error.detail == detail


@then("the registration should be refused without a status")
def step_refused_without_status(context):
    assert context.error is not None and context.error.status_code is None, context.error


@then('the new status should be "{status}"')
def step_new_status(context, status):
    assert context.new_status == status


@then('the service should have been asked to delete "{domain_id}"')
def step_asked_delete(context, domain_id):
    request = context.service_requests[-1]
    assert request.method == "DELETE" and request.url.path.endswith(f"/{domain_id}")
    assert context.deleted is True


@then("nothing should be left to delete")
def step_nothing_to_delete(context):
    assert context.deleted is False


# --- a workspace and the fake database ------------------------------------------


class _FakeSession:
    def __init__(self, organizations):
        self.organizations = organizations
        self.commit = AsyncMock()
        self.rollback = AsyncMock()

    async def execute(self, statement):
        result = MagicMock()
        first = self.organizations[0] if self.organizations else None
        result.scalar_one_or_none.return_value = first
        result.scalars.return_value.all.return_value = self.organizations
        return result

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _organization(context, domain, status, service_id=None):
    context.organization = Organization(
        id=uuid4(),
        name="Acme",
        slug="acme",
        plan=PlanType.ENTERPRISE,
        custom_domain=domain,
        custom_domain_status=CustomDomainStatus(status),
        custom_domain_service_id=service_id,
    )
    context.session = _FakeSession([context.organization])
    _patch(context, (webhooks, "async_session_factory"), lambda: context.session, attribute=True)

    # The delivery ids live in a set instead of Redis
    context.deliveries = set()

    async def already_processed(namespace, event_id):
        return (namespace, event_id) in context.deliveries

    async def mark_processed(namespace, event_id, ttl_seconds):
        context.deliveries.add((namespace, event_id))

    _patch(context, (webhooks.event_dedupe, "already_processed"), already_processed, attribute=True)
    _patch(context, (webhooks.event_dedupe, "mark_processed"), mark_processed, attribute=True)


@given('an organization with the custom domain "{domain}" in status "{status}"')
def step_organization(context, domain, status):
    # Notifications identify the domain by the id the service gave it
    _organization(context, domain, status, service_id="svc-1")


@given(
    'an organization linked to the service domain "{domain_id}" with the custom domain "{domain}" in status "{status}"'
)
def step_linked_organization(context, domain_id, domain, status):
    _organization(context, domain, status, service_id=domain_id)


@given('an organization with the custom domain "{domain}" not yet registered in the service')
def step_unregistered_organization(context, domain):
    _organization(context, domain, "active", service_id=None)


@then('the domain status should be "{status}"')
def step_status(context, status):
    assert context.organization.custom_domain_status == CustomDomainStatus(status)


@then('the domain error should mention "{text}"')
def step_error(context, text):
    assert text in (context.organization.custom_domain_error or "")


@then("the organization should have no custom domain")
def step_no_domain(context):
    assert context.organization.custom_domain is None
    assert context.organization.custom_domain_service_id is None


# --- the signed notifications ------------------------------------------------------


@given('the custom domain webhook secret is "{secret}"')
def step_secret(context, secret):
    settings = get_settings()
    _patch(context, (settings, "custom_domain_webhook_secret"), secret, attribute=True)
    _patch(context, (settings, "custom_domain_webhook_tolerance"), 300, attribute=True)
    _patch(context, (settings, "custom_domain_event_ttl"), 600, attribute=True)


@given("no custom domain webhook secret is configured")
def step_no_secret(context):
    _patch(context, (get_settings(), "custom_domain_webhook_secret"), "", attribute=True)


def _notification(context, name, error=None):
    context.delivery_counter = getattr(context, "delivery_counter", 0) + 1
    organization = context.organization
    status = {"domain.active": "active", "domain.failed": "failed"}.get(name, "deprovisioning")
    return json.dumps(
        {
            "id": f"delivery-{context.delivery_counter}",
            "event": name,
            "created_at": "2026-03-01T12:00:00+00:00",
            "domain": {
                "id": "svc-1",
                "domain": organization.custom_domain,
                "status": status,
                "client_id": "knowledge",
                "owner_id": str(organization.id),
                "owner_type": "organization",
                "error": error,
            },
            "data": {},
        }
    ).encode()


def _signature(body, secret=SECRET, timestamp=None):
    stamp = int(time.time()) if timestamp is None else timestamp
    digest = hmac.new(secret.encode(), f"{stamp}.".encode() + body, hashlib.sha256)
    return f"t={stamp},v1={digest.hexdigest()}"


def _deliver(context, body, header):
    context.last_delivery = (body, header)
    context.response = context.call(
        "POST",
        "/webhooks/custom-domain",
        content=body,
        headers={webhooks.SIGNATURE_HEADER: header, "Content-Type": "application/json"},
    )


@when('the service sends a signed "{name}" notification')
def step_notification(context, name):
    body = _notification(context, name)
    _deliver(context, body, _signature(body))


@when('the service sends a signed "{name}" notification with the error "{error}"')
def step_notification_error(context, name, error):
    body = _notification(context, name, error=error)
    _deliver(context, body, _signature(body))


@when("the service sends the same notification again")
def step_again(context):
    _deliver(context, *context.last_delivery)


@when('the domain status is set back to "{status}"')
def step_set_back(context, status):
    context.organization.custom_domain_status = CustomDomainStatus(status)


@when("a notification signed {hours:d} hour ago is played back")
def step_replay(context, hours):
    body = _notification(context, "domain.active")
    _deliver(context, body, _signature(body, timestamp=int(time.time()) - hours * 3600))


@when("a notification signed with another secret is received")
def step_forged(context):
    body = _notification(context, "domain.active")
    _deliver(context, body, _signature(body, secret="another-secret-of-thirty-two-characters"))


@then("the response should say the delivery is a duplicate")
def step_duplicate(context):
    assert context.response.json() == {"status": "duplicate"}, context.response.json()


# --- the reconciliation task ---------------------------------------------------------


@given('the service reports the domain "{domain_id}" as "{status}"')
def step_reports(context, domain_id, status):
    _client(
        context,
        lambda request: httpx.Response(
            200,
            json={"id": domain_id, "domain": "docs.acme.test", "status": status},
        ),
    )


@when("the reconciliation task runs")
def step_reconcile(context):
    if not hasattr(context, "service"):
        _client(context, lambda request: httpx.Response(500))
    engine = MagicMock()
    engine.dispose = AsyncMock()
    _patch(context, (tasks, "CustomDomainClient"), lambda: context.service, attribute=True)
    _patch(context, (tasks, "create_async_engine"), lambda url: engine, attribute=True)
    _patch(
        context,
        (tasks, "async_sessionmaker"),
        lambda *a, **k: lambda: context.session,
        attribute=True,
    )
    context.task_result = tasks.reconcile_custom_domains()


@then('the domain "{domain}" should have been registered')
def step_was_registered(context, domain):
    request = context.service_requests[-1]
    assert request.method == "POST" and json.loads(request.content)["domain"] == domain


@then("the organization should be linked to the service domain")
def step_linked(context):
    assert context.organization.custom_domain_service_id == "svc-1"
    assert context.organization.custom_domain_cname_target == "apps.example.test"

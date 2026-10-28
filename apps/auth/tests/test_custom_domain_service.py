# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for auth.services.custom_domain — the rules shared by the pages and the REST API."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from auth.db.models.tenant import CustomDomainStatus, WebhookEvent
from auth.services.custom_domain import (
    CustomDomainService,
    VerificationOutcome,
    is_valid_domain,
)

TASKS = "auth.tasks.custom_domain"


def _tenant(domain=None, status=None):
    tenant = MagicMock()
    tenant.id = uuid.uuid4()
    tenant.slug = "acme"
    tenant.display_name = "Acme"
    tenant.custom_domain = domain
    tenant.custom_domain_status = status
    tenant.custom_domain_verified_at = None
    tenant.custom_domain_ssl_at = None
    tenant.custom_domain_error = None
    tenant.custom_domain_checked_at = None
    return tenant


@pytest.fixture
def tasks():
    with (
        patch(f"{TASKS}.verify_custom_domain_dns") as verify,
        patch(f"{TASKS}.remove_custom_domain_config") as remove,
    ):
        yield verify, remove


@pytest.mark.parametrize(
    ("domain", "valid"),
    [
        ("auth.acme.example", True),
        ("acme.io", True),
        ("a-b.c-d.example.org", True),
        ("localhost", False),
        ("-acme.example", False),
        ("acme-.example", False),
        ("acme..example", False),
        ("acme.example/path", False),
        ("acme example.com", False),
        ("acme.123", False),
        ("a" * 64 + ".example", False),
        (("a" * 60 + ".") * 5 + "example", False),
    ],
)
def test_is_valid_domain(domain, valid):
    assert is_valid_domain(domain) is valid


class TestStatus:
    def test_without_a_domain_everything_is_none(self):
        assert CustomDomainService.status(_tenant()) == {
            "custom_domain": None,
            "status": None,
            "error": None,
            "verified_at": None,
            "ssl_at": None,
            "checked_at": None,
        }

    def test_a_populated_state(self):
        moment = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        tenant = _tenant("auth.acme.example", CustomDomainStatus.FAILED)
        tenant.custom_domain_error = "no CNAME"
        tenant.custom_domain_verified_at = moment
        tenant.custom_domain_ssl_at = moment
        tenant.custom_domain_checked_at = moment

        state = CustomDomainService.status(tenant)

        assert state["status"] == "failed"
        assert state["error"] == "no CNAME"
        assert state["verified_at"] == state["ssl_at"] == state["checked_at"] == moment.isoformat()


class TestSetDomain:
    async def test_a_new_domain_is_pending_announced_and_verified(self, tasks):
        verify, remove = tasks
        tenant = _tenant()
        actor, db, dispatch = uuid.uuid4(), AsyncMock(), AsyncMock()

        change = await CustomDomainService().set_domain(
            db, tenant, "auth.acme.example", actor_id=actor, dispatch=dispatch
        )

        assert (change.changed, change.old_domain, change.new_domain) == (
            True,
            None,
            "auth.acme.example",
        )
        assert tenant.custom_domain == "auth.acme.example"
        assert tenant.custom_domain_status is CustomDomainStatus.PENDING
        dispatch.assert_awaited_once_with(
            db,
            tenant_id=tenant.id,
            event=WebhookEvent.TENANT_UPDATED,
            data={
                "tenant_id": str(tenant.id),
                "display_name": "Acme",
                "custom_domain": "auth.acme.example",
                "actor_id": str(actor),
            },
        )
        db.commit.assert_awaited_once()
        verify.delay.assert_called_once_with(str(tenant.id), "auth.acme.example", "acme")
        remove.delay.assert_not_called()

    async def test_the_state_is_reset_when_the_domain_changes(self, tasks):
        tenant = _tenant("old.acme.example", CustomDomainStatus.ACTIVE)
        tenant.custom_domain_verified_at = tenant.custom_domain_ssl_at = datetime.now(UTC)
        tenant.custom_domain_error = "old error"
        tenant.custom_domain_checked_at = datetime.now(UTC)

        await CustomDomainService().set_domain(
            AsyncMock(), tenant, "new.acme.example", actor_id=uuid.uuid4(), dispatch=AsyncMock()
        )

        assert tenant.custom_domain_status is CustomDomainStatus.PENDING
        assert tenant.custom_domain_verified_at is None
        assert tenant.custom_domain_ssl_at is None
        assert tenant.custom_domain_error is None
        assert tenant.custom_domain_checked_at is None
        tasks[1].delay.assert_not_called()

    async def test_removing_the_domain_clears_the_state_and_queues_the_cleanup(self, tasks):
        verify, remove = tasks
        tenant = _tenant("old.acme.example", CustomDomainStatus.ACTIVE)
        db, dispatch = AsyncMock(), AsyncMock()

        change = await CustomDomainService().set_domain(
            db, tenant, None, actor_id=uuid.uuid4(), dispatch=dispatch
        )

        assert change.changed is True
        assert tenant.custom_domain is None
        assert tenant.custom_domain_status is None
        assert dispatch.await_args.kwargs["data"]["custom_domain"] is None
        db.commit.assert_awaited_once()
        remove.delay.assert_called_once_with("old.acme.example", "acme")
        verify.delay.assert_not_called()

    async def test_the_current_domain_changes_nothing(self, tasks):
        tenant = _tenant("acme.example", CustomDomainStatus.ACTIVE)
        db, dispatch = AsyncMock(), AsyncMock()

        change = await CustomDomainService().set_domain(
            db, tenant, "acme.example", actor_id=uuid.uuid4(), dispatch=dispatch
        )

        assert change.changed is False
        assert tenant.custom_domain_status is CustomDomainStatus.ACTIVE
        dispatch.assert_not_awaited()
        db.commit.assert_not_awaited()
        tasks[0].delay.assert_not_called()
        tasks[1].delay.assert_not_called()

    async def test_removing_nothing_changes_nothing(self, tasks):
        change = await CustomDomainService().set_domain(
            AsyncMock(), _tenant(), None, actor_id=uuid.uuid4(), dispatch=AsyncMock()
        )
        assert change.changed is False

    async def test_clearing_a_blank_stored_domain_queues_no_task(self, tasks):
        tenant = _tenant("")

        change = await CustomDomainService().set_domain(
            AsyncMock(), tenant, None, actor_id=uuid.uuid4(), dispatch=AsyncMock()
        )

        assert change.changed is True
        assert tenant.custom_domain is None
        tasks[0].delay.assert_not_called()
        tasks[1].delay.assert_not_called()

    async def test_the_default_dispatch_never_breaks_the_change(self, tasks):
        tenant = _tenant()
        db = AsyncMock()

        with patch(
            "auth.services.webhook.webhook_service.dispatch",
            AsyncMock(side_effect=RuntimeError("broker down")),
        ) as dispatch:
            change = await CustomDomainService().set_domain(
                db, tenant, "acme.example", actor_id=uuid.uuid4()
            )

        dispatch.assert_awaited_once()
        assert dispatch.await_args.kwargs["event"] == "tenant.updated"
        assert change.changed is True
        db.commit.assert_awaited_once()


class TestStartVerification:
    async def test_without_a_domain(self, tasks):
        db = AsyncMock()
        outcome = await CustomDomainService().start_verification(
            db, _tenant(), actor_id=uuid.uuid4()
        )
        assert outcome is VerificationOutcome.NO_DOMAIN
        db.commit.assert_not_awaited()

    async def test_an_active_domain_is_left_alone(self, tasks):
        tenant = _tenant("acme.example", CustomDomainStatus.ACTIVE)
        outcome = await CustomDomainService().start_verification(
            AsyncMock(), tenant, actor_id=uuid.uuid4()
        )
        assert outcome is VerificationOutcome.ALREADY_ACTIVE
        tasks[0].delay.assert_not_called()

    @pytest.mark.parametrize(
        "state", [CustomDomainStatus.DNS_VERIFYING, CustomDomainStatus.SSL_PROVISIONING]
    )
    async def test_a_running_verification_is_not_restarted(self, tasks, state):
        outcome = await CustomDomainService().start_verification(
            AsyncMock(), _tenant("acme.example", state), actor_id=uuid.uuid4()
        )
        assert outcome is VerificationOutcome.IN_PROGRESS
        tasks[0].delay.assert_not_called()

    @pytest.mark.parametrize("state", [None, CustomDomainStatus.PENDING, CustomDomainStatus.FAILED])
    async def test_otherwise_the_verification_is_queued(self, tasks, state):
        tenant = _tenant("acme.example", state)
        tenant.custom_domain_error = "no CNAME"
        db = AsyncMock()

        outcome = await CustomDomainService().start_verification(db, tenant, actor_id=uuid.uuid4())

        assert outcome is VerificationOutcome.STARTED
        assert tenant.custom_domain_status is CustomDomainStatus.PENDING
        assert tenant.custom_domain_error is None
        db.commit.assert_awaited_once()
        tasks[0].delay.assert_called_once_with(str(tenant.id), "acme.example", "acme")

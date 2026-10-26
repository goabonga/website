# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/tasks/custom_domain.py: the reconciliation with the service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.models.enums import CustomDomainStatus
from knowledge.services.custom_domain import (
    CustomDomainError,
    DomainDetails,
    RegisteredDomain,
)
from knowledge.tasks import custom_domain as tasks


def _organization(status=None, service_id=None, name="docs.example.test"):
    organization = MagicMock()
    organization.id = "11111111-1111-1111-1111-111111111111"
    organization.custom_domain = name
    organization.custom_domain_status = status
    organization.custom_domain_service_id = service_id
    organization.custom_domain_verified_at = None
    organization.custom_domain_ssl_at = None
    organization.custom_domain_error = None
    return organization


def _db(*organizations):
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(organizations)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _service(**methods):
    client = MagicMock()
    client.register = AsyncMock(
        return_value=RegisteredDomain(
            id="svc-1",
            domain="docs.example.test",
            status="pending",
            cname_target="apps.example.test",
        )
    )
    client.get = AsyncMock(return_value=DomainDetails(id="svc-1", domain="d", status="active"))
    for name, value in methods.items():
        setattr(client, name, value)
    return client


class TestReconcile:
    async def test_a_domain_the_service_does_not_know_is_registered(self):
        organization = _organization(status=CustomDomainStatus.ACTIVE)
        service = _service()

        counters = await tasks.reconcile(_db(organization), service)

        service.register.assert_awaited_once_with(
            "docs.example.test", "11111111-1111-1111-1111-111111111111"
        )
        assert organization.custom_domain_service_id == "svc-1"
        assert organization.custom_domain_cname_target == "apps.example.test"
        assert organization.custom_domain_status == CustomDomainStatus.PENDING
        assert counters == {"registered": 1, "updated": 0, "failed": 0, "errors": 0}

    async def test_a_domain_being_set_up_is_refreshed(self):
        organization = _organization(status=CustomDomainStatus.SSL_PROVISIONING, service_id="svc-1")
        service = _service()

        counters = await tasks.reconcile(_db(organization), service)

        service.get.assert_awaited_once_with("svc-1")
        service.register.assert_not_called()
        assert organization.custom_domain_status == CustomDomainStatus.ACTIVE
        assert counters["updated"] == 1

    async def test_the_failure_reason_of_the_service_is_kept(self):
        organization = _organization(status=CustomDomainStatus.DNS_VERIFYING, service_id="svc-1")
        service = _service(
            get=AsyncMock(
                return_value=DomainDetails(
                    id="svc-1", domain="d", status="failed", error_message="CNAME not found"
                )
            )
        )
        await tasks.reconcile(_db(organization), service)
        assert organization.custom_domain_status == CustomDomainStatus.FAILED
        assert organization.custom_domain_error == "CNAME not found"

    async def test_a_domain_the_service_lost_must_be_registered_again(self):
        organization = _organization(status=CustomDomainStatus.PENDING, service_id="svc-1")
        service = _service(get=AsyncMock(return_value=None))

        counters = await tasks.reconcile(_db(organization), service)

        assert organization.custom_domain_service_id is None
        assert organization.custom_domain_status == CustomDomainStatus.FAILED
        assert "register it again" in organization.custom_domain_error
        assert counters["failed"] == 1

    async def test_a_name_registered_by_someone_else_is_reported_to_the_customer(self):
        organization = _organization(status=CustomDomainStatus.PENDING)
        db = _db(organization)
        service = _service(
            register=AsyncMock(
                side_effect=CustomDomainError("Domain already registered", status_code=409)
            )
        )

        counters = await tasks.reconcile(db, service)

        assert organization.custom_domain_status == CustomDomainStatus.FAILED
        assert organization.custom_domain_error == "Domain already registered"
        assert counters["failed"] == 1
        db.rollback.assert_awaited_once()

    async def test_an_unreachable_service_is_counted_and_retried_next_time(self):
        organization = _organization(status=CustomDomainStatus.PENDING, service_id="svc-1")
        db = _db(organization)
        service = _service(get=AsyncMock(side_effect=CustomDomainError("down", retryable=True)))

        counters = await tasks.reconcile(db, service)

        assert counters["errors"] == 1
        assert organization.custom_domain_status == CustomDomainStatus.PENDING
        db.rollback.assert_awaited_once()

    async def test_one_failure_does_not_block_the_others(self):
        broken = _organization(status=CustomDomainStatus.PENDING, service_id="svc-1")
        fine = _organization(status=CustomDomainStatus.PENDING, service_id="svc-2")
        service = _service(
            get=AsyncMock(
                side_effect=[
                    RuntimeError("boom"),
                    DomainDetails(id="svc-2", domain="d", status="active"),
                ]
            )
        )

        counters = await tasks.reconcile(_db(broken, fine), service)

        assert counters["errors"] == 1
        assert counters["updated"] == 1
        assert fine.custom_domain_status == CustomDomainStatus.ACTIVE

    async def test_only_the_unregistered_and_the_unfinished_domains_are_selected(self):
        """Active and failed domains are left to the webhooks (checked on the SQL)."""
        db = _db()
        await tasks.reconcile(db, _service())

        sql = str(db.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "custom_domain IS NOT NULL" in sql
        assert "custom_domain_service_id IS NULL" in sql
        for status in ("pending", "dns_verifying", "dns_verified", "ssl_provisioning"):
            assert f"'{status}'" in sql
        assert "'active'" not in sql
        assert "'failed'" not in sql

    async def test_nothing_to_do(self):
        service = _service()
        counters = await tasks.reconcile(_db(), service)
        assert counters == {"registered": 0, "updated": 0, "failed": 0, "errors": 0}
        service.register.assert_not_called()
        service.get.assert_not_called()


class TestTask:
    def test_skipped_when_the_service_is_not_configured(self):
        client = MagicMock(is_configured=False)
        with patch.object(tasks, "CustomDomainClient", return_value=client):
            assert tasks.reconcile_custom_domains() == {"skipped": True}

    def test_reconciles_with_its_own_database_session(self):
        client = MagicMock(is_configured=True)
        engine = MagicMock()
        engine.dispose = AsyncMock()
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value="db")
        session.__aexit__ = AsyncMock(return_value=False)
        settings = MagicMock(database_url="postgresql+asyncpg://db")

        with (
            patch.object(tasks, "CustomDomainClient", return_value=client),
            patch.object(tasks, "get_settings", return_value=settings),
            patch.object(tasks, "create_async_engine", return_value=engine) as create,
            patch.object(tasks, "async_sessionmaker", return_value=lambda: session),
            patch.object(
                tasks, "reconcile", new=AsyncMock(return_value={"updated": 2})
            ) as reconcile,
        ):
            result = tasks.reconcile_custom_domains()

        assert result == {"updated": 2}
        create.assert_called_once_with("postgresql+asyncpg://db")
        reconcile.assert_awaited_once_with("db", client)
        engine.dispose.assert_awaited_once()

    def test_task_name_is_registered_and_scheduled(self):
        from knowledge.celery import celery_app

        celery_app.loader.import_default_modules()
        name = "knowledge.tasks.custom_domain.reconcile_custom_domains"
        assert name in celery_app.tasks
        assert any(e["task"] == name for e in celery_app.conf.beat_schedule.values())


@pytest.mark.parametrize("status", tasks.IN_PROGRESS)
def test_in_progress_statuses_are_not_final(status):
    assert status not in (CustomDomainStatus.ACTIVE, CustomDomainStatus.FAILED)

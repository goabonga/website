# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for knowledge/services/custom_domain.py: validation, statuses and the service client."""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
import pytest

from knowledge.models.enums import CustomDomainStatus
from knowledge.services import custom_domain
from knowledge.services.custom_domain import (
    CustomDomainClient,
    CustomDomainError,
    apply_status,
    clear_domain,
    get_custom_domain_client,
    map_status,
    validate_domain,
)
from knowledge.services.service_auth import ServiceAuthError

# ============================================================
# validate_domain (pure function)
# ============================================================


class TestValidateDomain:
    def test_valid_domain(self):
        valid, error = validate_domain("example.com")
        assert valid is True
        assert error == ""

    def test_empty_domain(self):
        valid, error = validate_domain("")
        assert valid is False
        assert "required" in error.lower()

    def test_domain_too_long(self):
        valid, error = validate_domain("a" * 254 + ".com")
        assert valid is False
        assert "too long" in error.lower()

    def test_invalid_format(self):
        valid, error = validate_domain("not a domain!")
        assert valid is False
        assert "invalid" in error.lower()

    def test_localhost_invalid(self):
        """localhost has no TLD so it fails regex validation."""
        valid, error = validate_domain("localhost")
        assert valid is False

    def test_dotlocal_reserved(self):
        valid, error = validate_domain("myapp.local")
        assert valid is False
        assert "reserved" in error.lower()

    def test_subdomain_valid(self):
        valid, error = validate_domain("docs.example.com")
        assert valid is True

    def test_hyphenated_domain(self):
        valid, error = validate_domain("my-app.example.com")
        assert valid is True

    def test_starts_with_hyphen_invalid(self):
        valid, error = validate_domain("-invalid.com")
        assert valid is False

    def test_numeric_tld(self):
        """TLD must be alphabetic only."""
        valid, error = validate_domain("example.123")
        assert valid is False


class TestValidateDomainReserved:
    @pytest.mark.parametrize("domain", ["localhost", "127.0.0.1", "0.0.0.0"])
    def test_local_addresses(self, domain):
        assert validate_domain(domain)[0] is False

    def test_case_and_spaces_are_normalized(self):
        assert validate_domain("  Docs.Example.COM ") == (True, "")


# ============================================================
# map_status / apply_status / clear_domain
# ============================================================


class TestMapStatus:
    @pytest.mark.parametrize(
        "status",
        ["pending", "dns_verifying", "dns_verified", "ssl_provisioning", "active", "failed"],
    )
    def test_statuses_of_the_application(self, status):
        assert map_status(status) == CustomDomainStatus(status)

    @pytest.mark.parametrize("status", ["suspended", "expired"])
    def test_other_failures_are_failed(self, status):
        assert map_status(status) == CustomDomainStatus.FAILED

    @pytest.mark.parametrize("status", ["deprovisioning", None, "something-new"])
    def test_statuses_that_are_not_recorded(self, status):
        assert map_status(status) is None


def _organization(**overrides):
    organization = MagicMock()
    organization.custom_domain_verified_at = None
    organization.custom_domain_ssl_at = None
    organization.custom_domain_error = "old"
    for key, value in overrides.items():
        setattr(organization, key, value)
    return organization


NOW = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


class TestApplyStatus:
    def test_pending_resets_the_dates_and_the_error(self):
        org = _organization(custom_domain_verified_at=NOW, custom_domain_ssl_at=NOW)
        assert apply_status(org, "pending", when=NOW) is True
        assert org.custom_domain_status == CustomDomainStatus.PENDING
        assert org.custom_domain_verified_at is None
        assert org.custom_domain_ssl_at is None
        assert org.custom_domain_error is None
        assert org.custom_domain_checked_at == NOW

    def test_dns_verified_records_when(self):
        org = _organization()
        apply_status(org, "dns_verified", when=NOW)
        assert org.custom_domain_verified_at == NOW
        assert org.custom_domain_ssl_at is None

    def test_active_records_both_dates_once(self):
        earlier = datetime(2026, 2, 1, tzinfo=UTC)
        org = _organization(custom_domain_verified_at=earlier)
        apply_status(org, "active", when=NOW)
        assert org.custom_domain_status == CustomDomainStatus.ACTIVE
        assert org.custom_domain_verified_at == earlier
        assert org.custom_domain_ssl_at == NOW
        apply_status(org, "active", when=datetime(2026, 4, 1, tzinfo=UTC))
        assert org.custom_domain_ssl_at == NOW

    def test_failed_keeps_the_reason(self):
        org = _organization()
        apply_status(org, "failed", error="CNAME not found", when=NOW)
        assert org.custom_domain_status == CustomDomainStatus.FAILED
        assert org.custom_domain_error == "CNAME not found"

    def test_failed_without_reason(self):
        org = _organization()
        apply_status(org, "failed", when=NOW)
        assert org.custom_domain_error == "Provisioning failed"

    def test_expired_explains_itself(self):
        org = _organization()
        apply_status(org, "expired", when=NOW)
        assert org.custom_domain_status == CustomDomainStatus.FAILED
        assert "expired" in org.custom_domain_error

    def test_error_is_truncated_to_the_column(self):
        org = _organization()
        apply_status(org, "failed", error="x" * 900, when=NOW)
        assert len(org.custom_domain_error) == 500

    def test_deprovisioning_is_not_recorded(self):
        org = _organization(custom_domain_status=CustomDomainStatus.ACTIVE)
        assert apply_status(org, "deprovisioning") is False
        assert org.custom_domain_status == CustomDomainStatus.ACTIVE

    def test_default_moment_is_now(self):
        org = _organization()
        apply_status(org, "pending")
        assert org.custom_domain_checked_at.tzinfo is not None


class TestClearDomain:
    def test_every_column_is_emptied(self):
        org = _organization(custom_domain="docs.example.test")
        clear_domain(org)
        for column in (
            "custom_domain",
            "custom_domain_status",
            "custom_domain_error",
            "custom_domain_verified_at",
            "custom_domain_ssl_at",
            "custom_domain_checked_at",
            "custom_domain_service_id",
            "custom_domain_cname_target",
        ):
            assert getattr(org, column) is None, column


# ============================================================
# CustomDomainClient
# ============================================================


def _settings(**overrides):
    settings = MagicMock()
    settings.custom_domain_service_url = "http://domains.test/"
    settings.custom_domain_service_socket_path = ""
    settings.service_timeout = 4.0
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


def _client(handler, **overrides) -> CustomDomainClient:
    with patch.object(custom_domain, "get_settings", return_value=_settings(**overrides)):
        client = CustomDomainClient()
    client._tokens = MagicMock()

    async def token(credentials, scope):
        client.scopes.append(scope)
        return "tok"

    client.scopes = []
    client._tokens.aget = token
    real = httpx.AsyncClient
    client._http_client = lambda: real(transport=httpx.MockTransport(handler))
    return client


def _json(status, body):
    return httpx.Response(status, json=body)


DOMAIN_ID = "6c1a2b3c-0000-4000-8000-000000000001"
CREATED = {
    "id": DOMAIN_ID,
    "domain": "docs.example.test",
    "status": "pending",
    "cname_target": "apps.example.test",
    "dns_instructions": "Create a CNAME record",
}


class TestConfiguration:
    def test_url_and_socket(self):
        assert _client(lambda r: None).base_url == "http://domains.test"
        socket = _client(lambda r: None, custom_domain_service_socket_path="/run/d.sock")
        assert socket.base_url == "http://localhost"
        assert socket.is_configured is True

    def test_not_configured(self):
        client = _client(
            lambda r: None, custom_domain_service_url="", custom_domain_service_socket_path=""
        )
        assert client.is_configured is False

    async def test_calls_fail_when_not_configured(self):
        client = _client(
            lambda r: None, custom_domain_service_url="", custom_domain_service_socket_path=""
        )
        with pytest.raises(CustomDomainError, match="not configured") as error:
            await client.register("docs.example.test", "org-1")
        assert error.value.retryable is False

    def test_http_clients(self):
        with patch.object(custom_domain, "get_settings", return_value=_settings()):
            client = CustomDomainClient()
        assert client._http_client().timeout.read == 4.0
        with patch.object(custom_domain.httpx, "AsyncHTTPTransport") as transport:
            client.socket_path = "/run/d.sock"
            client._http_client()
        transport.assert_called_once_with(uds="/run/d.sock")


class TestRegister:
    async def test_registers_the_domain_of_a_workspace(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return _json(201, CREATED)

        client = _client(handler)
        result = await client.register("docs.example.test", "org-1", metadata={"plan": "x"})

        request = seen["request"]
        assert request.method == "POST"
        assert str(request.url) == "http://domains.test/api/v1/domains"
        assert request.headers["authorization"] == "Bearer tok"
        assert json.loads(request.content) == {
            "domain": "docs.example.test",
            "owner_id": "org-1",
            "owner_type": "organization",
            "metadata": {"plan": "x"},
        }
        assert client.scopes == ["custom-domain:write"]
        assert result.id == DOMAIN_ID
        assert result.cname_target == "apps.example.test"
        assert result.dns_instructions == "Create a CNAME record"

    async def test_the_body_names_no_upstream_or_cname(self):
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return _json(201, CREATED)

        await _client(handler).register("docs.example.test", "org-1")
        assert set(seen["body"]) == {"domain", "owner_id", "owner_type"}

    @pytest.mark.parametrize(
        ("status", "retryable"),
        [(409, False), (403, False), (400, False), (422, False), (429, True), (503, True)],
    )
    async def test_refusals(self, status, retryable):
        client = _client(lambda r: _json(status, {"detail": "because"}))
        with pytest.raises(CustomDomainError, match="because") as error:
            await client.register("docs.example.test", "org-1")
        assert error.value.status_code == status
        assert error.value.retryable is retryable

    async def test_answer_without_detail(self):
        client = _client(lambda r: httpx.Response(502, text="bad gateway"))
        with pytest.raises(CustomDomainError, match="502"):
            await client.register("docs.example.test", "org-1")

    async def test_unexpected_success_body(self):
        client = _client(lambda r: _json(201, {"nope": 1}))
        with pytest.raises(CustomDomainError, match="Unexpected"):
            await client.register("docs.example.test", "org-1")

    async def test_body_that_is_not_json(self):
        client = _client(lambda r: httpx.Response(201, text="x"))
        with pytest.raises(CustomDomainError, match="Unexpected"):
            await client.register("docs.example.test", "org-1")

    async def test_network_error_can_pass(self):
        def handler(request):
            raise httpx.ConnectError("down")

        with pytest.raises(CustomDomainError, match="request failed") as error:
            await _client(handler).register("docs.example.test", "org-1")
        assert error.value.retryable is True

    @pytest.mark.parametrize("retryable", [True, False])
    async def test_token_failure(self, retryable):
        client = _client(lambda r: None)

        async def failing(credentials, scope):
            raise ServiceAuthError("no token", retryable=retryable)

        client._tokens.aget = failing
        with pytest.raises(CustomDomainError, match="no token") as error:
            await client.register("docs.example.test", "org-1")
        assert error.value.retryable is retryable

    async def test_expired_token_is_renewed_once(self):
        answers = [_json(401, {"detail": "expired"}), _json(201, CREATED)]
        client = _client(lambda r: answers.pop(0))
        result = await client.register("docs.example.test", "org-1")
        assert result.id == DOMAIN_ID
        client._tokens.clear.assert_called_once()

    async def test_token_refused_twice(self):
        client = _client(lambda r: _json(401, {"detail": "no"}))
        with pytest.raises(CustomDomainError) as error:
            await client.register("docs.example.test", "org-1")
        assert error.value.status_code == 401


class TestRead:
    async def test_get_a_domain(self):
        details = {
            "id": DOMAIN_ID,
            "domain": "docs.example.test",
            "status": "failed",
            "error_message": "CNAME missing",
            "dns_verified_at": None,
            "ssl_provisioned_at": None,
            "cname_target": "apps.example.test",
        }
        seen = {}

        def handler(request):
            seen["request"] = request
            return _json(200, details)

        client = _client(handler)
        result = await client.get(DOMAIN_ID)
        assert str(seen["request"].url) == f"http://domains.test/api/v1/domains/{DOMAIN_ID}"
        assert client.scopes == ["custom-domain:read"]
        assert result.status == "failed"
        assert result.error_message == "CNAME missing"
        assert result.cname_target == "apps.example.test"

    async def test_unknown_domain(self):
        assert await _client(lambda r: _json(404, {"detail": "Domain not found"})).get("x") is None

    async def test_service_error(self):
        with pytest.raises(CustomDomainError) as error:
            await _client(lambda r: _json(500, {"detail": "boom"})).get("x")
        assert error.value.retryable is True

    async def test_list_domains(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return _json(200, {"items": [{"id": "a"}, {"id": "b"}], "total": 2})

        items = await _client(handler).list_domains(owner_id="org-1", limit=10)
        assert [item["id"] for item in items] == ["a", "b"]
        assert seen["url"] == "http://domains.test/api/v1/domains?limit=10&owner_id=org-1"

    async def test_list_domains_without_owner(self):
        seen = {}

        def handler(request):
            seen["url"] = str(request.url)
            return _json(200, {"items": []})

        assert await _client(handler).list_domains() == []
        assert seen["url"].endswith("?limit=100")


class TestVerifyAndDelete:
    async def test_verify_restarts_the_verification(self):
        seen = {}

        def handler(request):
            seen["request"] = request
            return _json(200, {"id": DOMAIN_ID, "status": "dns_verifying", "message": "ok"})

        client = _client(handler)
        assert await client.verify(DOMAIN_ID) == "dns_verifying"
        assert seen["request"].method == "POST"
        assert seen["request"].url.path.endswith(f"/{DOMAIN_ID}/verify")
        assert client.scopes == ["custom-domain:write"]

    async def test_verify_refused_in_this_status(self):
        client = _client(lambda r: _json(400, {"detail": "Cannot verify domain in status active"}))
        with pytest.raises(CustomDomainError, match="Cannot verify"):
            await client.verify(DOMAIN_ID)

    async def test_delete_is_accepted(self):
        seen = {}

        def handler(request):
            seen["method"] = request.method
            return _json(202, {"id": DOMAIN_ID, "status": "deprovisioning"})

        assert await _client(handler).delete(DOMAIN_ID) is True
        assert seen["method"] == "DELETE"

    async def test_delete_of_an_unknown_domain_is_already_done(self):
        assert (
            await _client(lambda r: _json(404, {"detail": "Domain not found"})).delete("x") is False
        )

    async def test_delete_failure(self):
        with pytest.raises(CustomDomainError):
            await _client(lambda r: _json(403, {"detail": "Access denied"})).delete("x")


def test_get_custom_domain_client_is_a_singleton():
    custom_domain._client = None
    with patch.object(custom_domain, "get_settings", return_value=_settings()):
        first = get_custom_domain_client()
        assert get_custom_domain_client() is first
    custom_domain._client = None

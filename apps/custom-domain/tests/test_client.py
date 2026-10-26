# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Tests for custom_domain/client/client.py and custom_domain/client/__init__.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from custom_domain.client.client import (
    AsyncCustomDomainClient,
    AuthenticationError,
    AuthorizationError,
    Client,
    ClientList,
    ClientsAPI,
    ConflictError,
    CustomDomainClient,
    CustomDomainError,
    Domain,
    DomainCreate,
    DomainList,
    DomainLookup,
    DomainsAPI,
    DomainStats,
    DomainStatus,
    DomainStatus_,
    NotFoundError,
    OverviewStats,
    SSEEvent,
    StatsAPI,
    Template,
    TemplateList,
    TemplatesAPI,
    ValidationError,
    _parse_datetime,
)

# ============================================================
# _parse_datetime tests
# ============================================================


class TestParseDatetime:
    """Tests for _parse_datetime helper."""

    def test_none_value(self):
        assert _parse_datetime(None) is None

    def test_empty_string(self):
        assert _parse_datetime("") is None

    def test_iso_format(self):
        result = _parse_datetime("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1

    def test_z_suffix(self):
        result = _parse_datetime("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2024

    def test_invalid_format(self):
        assert _parse_datetime("not-a-date") is None


# ============================================================
# Data model tests
# ============================================================


class TestDomain:
    """Tests for Domain dataclass."""

    def test_from_dict_minimal(self):
        data = {
            "id": "d1",
            "domain": "example.com",
            "status": "active",
        }
        d = Domain.from_dict(data)
        assert d.id == "d1"
        assert d.domain == "example.com"
        assert d.status == DomainStatus.ACTIVE
        assert d.client_id == ""
        assert d.error_message is None

    def test_from_dict_full(self):
        data = {
            "id": "d2",
            "domain": "app.example.com",
            "client_id": "c1",
            "owner_id": "org_1",
            "owner_type": "organization",
            "upstream_target": "http://localhost:8000",
            "cname_target": "apps.example.com",
            "status": "pending",
            "error_message": "DNS check failed",
            "dns_verified_at": "2024-01-15T10:00:00Z",
            "ssl_provisioned_at": None,
            "ssl_expires_at": None,
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "deleted_at": None,
            "metadata": {"key": "value"},
        }
        d = Domain.from_dict(data)
        assert d.owner_id == "org_1"
        assert d.status == DomainStatus.PENDING
        assert d.error_message == "DNS check failed"
        assert d.dns_verified_at is not None
        assert d.metadata == {"key": "value"}


class TestDomainCreate:
    """Tests for DomainCreate dataclass."""

    def test_from_dict(self):
        data = {
            "id": "d1",
            "domain": "new.example.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
            "created_at": "2024-01-15T09:00:00Z",
            "dns_instructions": "Add a CNAME record",
        }
        dc = DomainCreate.from_dict(data)
        assert dc.id == "d1"
        assert dc.dns_instructions == "Add a CNAME record"
        assert dc.created_at is not None

    def test_from_dict_minimal(self):
        data = {
            "id": "d2",
            "domain": "min.example.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_2",
            "owner_type": "user",
        }
        dc = DomainCreate.from_dict(data)
        assert dc.dns_instructions is None
        assert dc.created_at is None


class TestDomainStatusModel:
    """Tests for DomainStatus_ dataclass."""

    def test_from_dict(self):
        data = {
            "id": "d1",
            "domain": "example.com",
            "status": "dns_verifying",
            "error_message": None,
            "retry_count": 3,
            "last_check_at": "2024-01-15T10:00:00Z",
            "dns_verified_at": None,
            "ssl_provisioned_at": None,
            "ssl_expires_at": None,
        }
        ds = DomainStatus_.from_dict(data)
        assert ds.status == DomainStatus.DNS_VERIFYING
        assert ds.retry_count == 3
        assert ds.last_check_at is not None

    def test_from_dict_defaults(self):
        data = {"id": "d2", "domain": "min.com", "status": "pending"}
        ds = DomainStatus_.from_dict(data)
        assert ds.retry_count == 0
        assert ds.error_message is None


class TestDomainLookup:
    """Tests for DomainLookup dataclass."""

    def test_from_dict(self):
        data = {
            "domain": "example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
            "client_id": "c1",
            "status": "active",
            "metadata": {"x": 1},
        }
        dl = DomainLookup.from_dict(data)
        assert dl.domain == "example.com"
        assert dl.metadata == {"x": 1}

    def test_from_dict_no_metadata(self):
        data = {
            "domain": "example.com",
            "owner_id": "org_1",
            "owner_type": "user",
            "client_id": "c1",
            "status": "pending",
        }
        dl = DomainLookup.from_dict(data)
        assert dl.metadata is None


class TestDomainList:
    """Tests for DomainList dataclass."""

    def test_from_dict(self):
        data = {
            "items": [
                {"id": "d1", "domain": "a.com", "status": "active"},
                {"id": "d2", "domain": "b.com", "status": "pending"},
            ],
            "total": 2,
            "limit": 20,
            "offset": 0,
        }
        dl = DomainList.from_dict(data)
        assert dl.total == 2
        assert len(dl.items) == 2
        assert dl.items[0].domain == "a.com"

    def test_from_dict_empty(self):
        data = {"items": [], "total": 0, "limit": 20, "offset": 0}
        dl = DomainList.from_dict(data)
        assert dl.total == 0
        assert len(dl.items) == 0


class TestClientModel:
    """Tests for Client dataclass."""

    def test_from_dict_full(self):
        data = {
            "id": 1,
            "client_id": "c1",
            "name": "Client One",
            "description": "Test client",
            "default_upstream_target": "http://localhost",
            "default_cname_target": "apps.example.com",
            "default_nginx_template_id": 1,
            "max_domains": 10,
            "is_active": True,
            "domains_count": 5,
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
            "metadata": {"key": "val"},
        }
        c = Client.from_dict(data)
        assert c.id == 1
        assert c.client_id == "c1"
        assert c.max_domains == 10
        assert c.domains_count == 5
        assert c.metadata == {"key": "val"}

    def test_from_dict_defaults(self):
        data = {"id": 2, "client_id": "c2", "name": "Minimal"}
        c = Client.from_dict(data)
        assert c.is_active is True
        assert c.domains_count == 0
        assert c.description is None


class TestClientList:
    """Tests for ClientList dataclass."""

    def test_from_dict(self):
        data = {
            "items": [{"id": 1, "client_id": "c1", "name": "One"}],
            "total": 1,
        }
        cl = ClientList.from_dict(data)
        assert cl.total == 1
        assert cl.items[0].client_id == "c1"


class TestTemplateModel:
    """Tests for Template dataclass."""

    def test_from_dict_full(self):
        data = {
            "id": 1,
            "name": "Default",
            "description": "Desc",
            "http_template": "server {}",
            "https_template": "server ssl {}",
            "is_default": True,
            "is_active": True,
            "created_at": "2024-01-15T09:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z",
        }
        t = Template.from_dict(data)
        assert t.is_default is True
        assert t.http_template == "server {}"

    def test_from_dict_defaults(self):
        data = {"id": 2, "name": "Custom"}
        t = Template.from_dict(data)
        assert t.is_default is False
        assert t.is_active is True
        assert t.description is None


class TestTemplateList:
    """Tests for TemplateList dataclass."""

    def test_from_dict(self):
        data = {"items": [{"id": 1, "name": "T1"}], "total": 1}
        tl = TemplateList.from_dict(data)
        assert tl.total == 1


class TestDomainStats:
    """Tests for DomainStats dataclass."""

    def test_from_dict(self):
        data = {
            "total": 100,
            "active": 80,
            "pending": 10,
            "failed": 5,
            "deleted": 5,
            "by_status": {"active": 80, "pending": 10},
            "created_last_24h": 2,
            "created_last_7d": 10,
            "created_last_30d": 30,
            "activated_last_24h": 1,
            "activated_last_7d": 8,
            "ssl_expiring_soon": 3,
            "ssl_expired": 1,
        }
        ds = DomainStats.from_dict(data)
        assert ds.total == 100
        assert ds.ssl_expiring_soon == 3


class TestOverviewStats:
    """Tests for OverviewStats dataclass."""

    def test_from_dict(self):
        data = {
            "domains": {
                "total": 10,
                "active": 8,
                "pending": 1,
                "failed": 1,
                "deleted": 0,
                "by_status": {},
                "created_last_24h": 0,
                "created_last_7d": 2,
                "created_last_30d": 5,
                "activated_last_24h": 0,
                "activated_last_7d": 1,
                "ssl_expiring_soon": 0,
                "ssl_expired": 0,
            },
            "clients": {"total": 3},
            "templates": {"total": 2},
        }
        o = OverviewStats.from_dict(data)
        assert o.domains.total == 10
        assert o.clients == {"total": 3}


class TestSSEEvent:
    """Tests for SSEEvent dataclass."""

    def test_from_dict(self):
        data = {
            "type": "domain.updated",
            "payload": {"domain_id": "d1", "timestamp": "2024-01-15T10:00:00Z"},
        }
        e = SSEEvent.from_dict(data)
        assert e.event_type == "domain.updated"
        assert e.timestamp is not None

    def test_from_dict_defaults(self):
        data = {}
        e = SSEEvent.from_dict(data)
        assert e.event_type == "unknown"
        assert e.payload == {}
        assert e.timestamp is None


# ============================================================
# Exception tests
# ============================================================


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_custom_domain_error(self):
        err = CustomDomainError("msg", status_code=500, detail="detail")
        assert str(err) == "msg"
        assert err.status_code == 500
        assert err.detail == "detail"

    def test_authentication_error(self):
        err = AuthenticationError("auth failed", status_code=401)
        assert isinstance(err, CustomDomainError)
        assert err.status_code == 401

    def test_authorization_error(self):
        err = AuthorizationError("forbidden", status_code=403)
        assert isinstance(err, CustomDomainError)

    def test_not_found_error(self):
        err = NotFoundError("not found", status_code=404)
        assert isinstance(err, CustomDomainError)

    def test_conflict_error(self):
        err = ConflictError("conflict", status_code=409)
        assert isinstance(err, CustomDomainError)

    def test_validation_error(self):
        err = ValidationError("invalid", status_code=400)
        assert isinstance(err, CustomDomainError)


# ============================================================
# CustomDomainClient tests
# ============================================================


class TestCustomDomainClient:
    """Tests for sync CustomDomainClient."""

    def test_init(self):
        client = CustomDomainClient(
            base_url="https://api.example.com/",
            access_token="token123",
            timeout=60,
        )
        assert client.base_url == "https://api.example.com"
        assert client.access_token == "token123"
        assert client.timeout == 60
        assert isinstance(client.domains, DomainsAPI)
        assert isinstance(client.clients, ClientsAPI)
        assert isinstance(client.templates, TemplatesAPI)
        assert isinstance(client.stats, StatsAPI)
        client.close()

    def test_init_with_token_refresher(self):
        def refresher():
            return "new-token"

        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="old-token",
            token_refresher=refresher,
        )
        assert client.token_refresher is refresher
        client.close()

    def test_context_manager(self):
        with CustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        ) as client:
            assert isinstance(client, CustomDomainClient)

    def test_request_success(self):
        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "ok"}

        with patch.object(client._http, "request", return_value=mock_response):
            result = client._request("GET", "/test")
            assert result == {"data": "ok"}
        client.close()

    def test_request_204_returns_none(self):
        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(client._http, "request", return_value=mock_response):
            result = client._request("DELETE", "/test")
            assert result is None
        client.close()

    def test_request_401_with_token_refresher(self):
        refresh_called = []

        def refresher():
            refresh_called.append(True)
            return "new-token"

        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="old-token",
            token_refresher=refresher,
        )

        # First call returns 401, second call returns 200
        mock_401 = MagicMock()
        mock_401.status_code = 401
        mock_401.json.return_value = {"detail": "expired"}
        mock_401.text = "expired"

        mock_200 = MagicMock()
        mock_200.status_code = 200
        mock_200.json.return_value = {"data": "refreshed"}

        with patch.object(client._http, "request", side_effect=[mock_401, mock_200]):
            result = client._request("GET", "/test")
            assert result == {"data": "refreshed"}
            assert len(refresh_called) == 1
            assert client.access_token == "new-token"
        client.close()

    def test_request_401_without_refresher(self):
        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "unauthorized"}
        mock_response.text = "unauthorized"

        with (
            patch.object(client._http, "request", return_value=mock_response),
            pytest.raises(AuthenticationError),
        ):
            client._request("GET", "/test")
        client.close()

    def test_request_401_retry_still_401(self):
        """401 after token refresh should not retry again."""
        client = CustomDomainClient(
            base_url="https://api.example.com",
            access_token="old-token",
            token_refresher=lambda: "new-token",
        )

        mock_401 = MagicMock()
        mock_401.status_code = 401
        mock_401.json.return_value = {"detail": "still unauthorized"}
        mock_401.text = "still unauthorized"

        with (
            patch.object(client._http, "request", return_value=mock_401),
            pytest.raises(AuthenticationError),
        ):
            client._request("GET", "/test")
        client.close()

    def test_handle_error_403(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "forbidden"}
        mock_response.text = "forbidden"

        with pytest.raises(AuthorizationError):
            client._handle_error(mock_response)
        client.close()

    def test_handle_error_404(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"detail": "not found"}
        mock_response.text = "not found"

        with pytest.raises(NotFoundError):
            client._handle_error(mock_response)
        client.close()

    def test_handle_error_409(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.json.return_value = {"detail": "conflict"}
        mock_response.text = "conflict"

        with pytest.raises(ConflictError):
            client._handle_error(mock_response)
        client.close()

    def test_handle_error_400(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "bad request"}
        mock_response.text = "bad request"

        with pytest.raises(ValidationError):
            client._handle_error(mock_response)
        client.close()

    def test_handle_error_500(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "server error"}
        mock_response.text = "server error"

        with pytest.raises(CustomDomainError):
            client._handle_error(mock_response)
        client.close()

    def test_handle_error_json_parse_fails(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("not json")
        mock_response.text = "plain text error"

        with pytest.raises(CustomDomainError) as exc_info:
            client._handle_error(mock_response)
        assert "plain text error" in str(exc_info.value)
        client.close()

    def test_health(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="token")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client._http, "get", return_value=mock_response):
            result = client.health()
            assert result == {"status": "ok"}
        client.close()


# ============================================================
# DomainsAPI tests
# ============================================================


class TestDomainsAPI:
    """Tests for DomainsAPI."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_list_domains(self):
        client = self._make_client()
        response_data = {
            "items": [{"id": "d1", "domain": "a.com", "status": "active"}],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.list()
            assert result.total == 1
        client.close()

    def test_list_domains_with_filters(self):
        client = self._make_client()
        response_data = {"items": [], "total": 0, "limit": 10, "offset": 5}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.domains.list(
                status=DomainStatus.ACTIVE,
                owner_id="org_1",
                include_deleted=True,
                limit=10,
                offset=5,
            )
            call_args = mock_req.call_args
            params = call_args[1]["params"] if "params" in call_args[1] else call_args[0][2]
            assert params["status_filter"] == "active"
            assert params["owner_id"] == "org_1"
            assert params["include_deleted"] is True
        client.close()

    def test_create_domain(self):
        client = self._make_client()
        response_data = {
            "id": "d1",
            "domain": "new.example.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.create(
                domain="new.example.com",
                owner_id="org_1",
                owner_type="organization",
            )
            assert result.domain == "new.example.com"
        client.close()

    def test_create_domain_with_all_options(self):
        client = self._make_client()
        response_data = {
            "id": "d1",
            "domain": "new.example.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
        }
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.domains.create(
                domain="new.example.com",
                owner_id="org_1",
                owner_type="organization",
                upstream_target="http://localhost",
                cname_target="apps.example.com",
                nginx_template_id=1,
                metadata={"key": "val"},
            )
            call_args = mock_req.call_args
            json_data = call_args[1]["json"] if "json" in call_args[1] else call_args[0][2]
            assert json_data["upstream_target"] == "http://localhost"
            assert json_data["nginx_template_id"] == 1
            assert json_data["metadata"] == {"key": "val"}
        client.close()

    def test_get_domain(self):
        client = self._make_client()
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.get("d1")
            assert result.id == "d1"
        client.close()

    def test_update_domain(self):
        client = self._make_client()
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            result = client.domains.update(
                "d1",
                upstream_target="http://new-upstream",
                nginx_template_id=2,
                metadata={"updated": True},
            )
            assert result.id == "d1"
            json_data = (
                mock_req.call_args[1]["json"]
                if "json" in mock_req.call_args[1]
                else mock_req.call_args[0][3]
            )
            assert json_data["upstream_target"] == "http://new-upstream"
        client.close()

    def test_delete_domain(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value=None):
            client.domains.delete("d1")
        client.close()

    def test_lookup_domain(self):
        client = self._make_client()
        response_data = {
            "domain": "example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
            "client_id": "c1",
            "status": "active",
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.lookup("example.com")
            assert result.domain == "example.com"
        client.close()

    def test_verify_domain(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={"status": "verifying"}):
            result = client.domains.verify("d1")
            assert result["status"] == "verifying"
        client.close()

    def test_provision_domain(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={"status": "provisioning"}):
            result = client.domains.provision("d1")
            assert result["status"] == "provisioning"
        client.close()

    def test_get_status(self):
        client = self._make_client()
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.get_status("d1")
            assert result.status == DomainStatus.ACTIVE
        client.close()

    def test_get_event_history(self):
        client = self._make_client()
        response_data = {
            "events": [
                {"type": "domain.created", "payload": {"domain_id": "d1"}},
            ]
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.domains.get_event_history("d1", limit=10)
            assert len(result) == 1
            assert result[0].event_type == "domain.created"
        client.close()

    def test_get_event_history_empty(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={}):
            result = client.domains.get_event_history("d1")
            assert result == []
        client.close()


# ============================================================
# DomainsAPI SSE + wait_for_active tests
# ============================================================


class TestDomainsAPISSE:
    """Tests for stream_events and _parse_sse_event."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_parse_sse_event_valid(self):
        client = self._make_client()
        event_str = 'event: domain.updated\ndata: {"type": "domain.updated", "payload": {"domain_id": "d1"}}'
        result = client.domains._parse_sse_event(event_str)
        assert result is not None
        assert result.event_type == "domain.updated"
        client.close()

    def test_parse_sse_event_no_data(self):
        client = self._make_client()
        event_str = "event: heartbeat\n: comment"
        result = client.domains._parse_sse_event(event_str)
        assert result is None
        client.close()

    def test_parse_sse_event_invalid_json(self):
        client = self._make_client()
        event_str = "data: not-json"
        result = client.domains._parse_sse_event(event_str)
        assert result is None
        client.close()

    def test_parse_sse_event_data_only(self):
        client = self._make_client()
        event_str = 'data: {"type": "status_change", "payload": {"status": "active"}}'
        result = client.domains._parse_sse_event(event_str)
        assert result is not None
        assert result.event_type == "status_change"
        client.close()

    def test_stream_events(self):
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_text.return_value = [
            'data: {"type": "domain.updated", "payload": {"domain_id": "d1"}}\n\n',
            'data: {"type": "domain.active", "payload": {"domain_id": "d1"}}\n\n',
        ]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("custom_domain.client.client.httpx.stream", return_value=mock_response):
            events = list(client.domains.stream_events("d1"))
            assert len(events) == 2
            assert events[0].event_type == "domain.updated"
        client.close()

    def test_stream_events_with_partial_chunks(self):
        """Test SSE parsing when event is split across chunks."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        # Event split across two chunks
        mock_response.iter_text.return_value = [
            'data: {"type": "ev1", "payload": {}}',
            '\n\ndata: {"type": "ev2", "payload": {}}\n\n',
        ]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("custom_domain.client.client.httpx.stream", return_value=mock_response):
            events = list(client.domains.stream_events("d1"))
            assert len(events) == 2
        client.close()

    def test_stream_events_skips_unparseable_event(self):
        """Test SSE skips events that parse to None (branch 562->559)."""
        client = self._make_client()

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        # First event has no data line -> _parse_sse_event returns None
        # Second event is valid
        mock_response.iter_text.return_value = [
            ': heartbeat\n\ndata: {"type": "valid", "payload": {}}\n\n',
        ]
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("custom_domain.client.client.httpx.stream", return_value=mock_response):
            events = list(client.domains.stream_events("d1"))
            assert len(events) == 1
            assert events[0].event_type == "valid"
        client.close()


class TestWaitForActive:
    """Tests for DomainsAPI.wait_for_active."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_wait_for_active_immediate(self):
        client = self._make_client()
        status_data = {"id": "d1", "domain": "a.com", "status": "active"}
        domain_data = {"id": "d1", "domain": "a.com", "status": "active"}

        status = DomainStatus_.from_dict(status_data)
        domain = Domain.from_dict(domain_data)

        with (
            patch.object(client.domains, "get_status", return_value=status),
            patch.object(client.domains, "get", return_value=domain),
        ):
            result = client.domains.wait_for_active("d1")
            assert result.id == "d1"
        client.close()

    def test_wait_for_active_fails(self):
        client = self._make_client()
        status_data = {
            "id": "d1",
            "domain": "a.com",
            "status": "failed",
            "error_message": "DNS timeout",
        }
        status = DomainStatus_.from_dict(status_data)

        with (
            patch.object(client.domains, "get_status", return_value=status),
            pytest.raises(CustomDomainError, match="DNS timeout"),
        ):
            client.domains.wait_for_active("d1")
        client.close()

    def test_wait_for_active_timeout(self):
        client = self._make_client()
        status_data = {"id": "d1", "domain": "a.com", "status": "pending"}
        status = DomainStatus_.from_dict(status_data)

        with (
            patch.object(client.domains, "get_status", return_value=status),
            patch("custom_domain.client.client.time.sleep"),
            patch("custom_domain.client.client.time.time", side_effect=[0, 0, 100]),
            pytest.raises(CustomDomainError, match="Timeout"),
        ):
            client.domains.wait_for_active("d1", timeout=10)
        client.close()

    def test_wait_for_active_with_callback(self):
        client = self._make_client()
        callbacks = []

        pending_status = DomainStatus_.from_dict(
            {"id": "d1", "domain": "a.com", "status": "pending"}
        )
        active_status = DomainStatus_.from_dict({"id": "d1", "domain": "a.com", "status": "active"})
        domain = Domain.from_dict({"id": "d1", "domain": "a.com", "status": "active"})

        call_count = 0

        def get_status_side_effect(domain_id):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return pending_status
            return active_status

        with (
            patch.object(client.domains, "get_status", side_effect=get_status_side_effect),
            patch.object(client.domains, "get", return_value=domain),
            patch("custom_domain.client.client.time.sleep"),
            patch("custom_domain.client.client.time.time", side_effect=[0, 0, 0, 0, 0]),
        ):
            result = client.domains.wait_for_active("d1", on_status_change=callbacks.append)
            assert result.id == "d1"
            assert len(callbacks) == 2  # pending -> active

        client.close()

    def test_wait_for_active_status_unchanged_no_callback(self):
        """Callback only fires on status changes, not on every poll."""
        client = self._make_client()
        callbacks = []

        pending_status = DomainStatus_.from_dict(
            {"id": "d1", "domain": "a.com", "status": "pending"}
        )
        active_status = DomainStatus_.from_dict({"id": "d1", "domain": "a.com", "status": "active"})
        domain = Domain.from_dict({"id": "d1", "domain": "a.com", "status": "active"})

        call_count = 0

        def get_status_side_effect(domain_id):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return pending_status
            return active_status

        with (
            patch.object(client.domains, "get_status", side_effect=get_status_side_effect),
            patch.object(client.domains, "get", return_value=domain),
            patch("custom_domain.client.client.time.sleep"),
            patch("custom_domain.client.client.time.time", side_effect=[0, 0, 0, 0, 0, 0]),
        ):
            client.domains.wait_for_active("d1", on_status_change=callbacks.append)
            # Only 2 callbacks: first pending, then active (second pending is same status)
            assert len(callbacks) == 2

        client.close()


# ============================================================
# ClientsAPI tests
# ============================================================


class TestClientsAPI:
    """Tests for ClientsAPI."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_list(self):
        client = self._make_client()
        response_data = {
            "items": [{"id": 1, "client_id": "c1", "name": "One"}],
            "total": 1,
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.clients.list()
            assert result.total == 1
        client.close()

    def test_create_minimal(self):
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "New"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            result = client.clients.create(client_id="c1", name="New")
            assert result.client_id == "c1"
            json_data = mock_req.call_args[1].get(
                "json", mock_req.call_args[0][2] if len(mock_req.call_args[0]) > 2 else {}
            )
            assert "description" not in json_data
        client.close()

    def test_create_full(self):
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "Full"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.clients.create(
                client_id="c1",
                name="Full",
                description="desc",
                default_upstream_target="http://upstream",
                default_cname_target="cname.example.com",
                default_nginx_template_id=1,
                max_domains=10,
                metadata={"k": "v"},
            )
            json_data = mock_req.call_args.kwargs.get(
                "json", mock_req.call_args.args[2] if len(mock_req.call_args.args) > 2 else {}
            )
            assert json_data["description"] == "desc"
            assert json_data["max_domains"] == 10
            assert json_data["metadata"] == {"k": "v"}
        client.close()

    def test_get(self):
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "One"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.clients.get(1)
            assert result.id == 1
        client.close()

    def test_update(self):
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "Updated"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            result = client.clients.update(
                1,
                name="Updated",
                description="new desc",
                default_upstream_target="http://new",
                default_cname_target="new.example.com",
                default_nginx_template_id=2,
                max_domains=20,
                metadata={"updated": True},
            )
            assert result.name == "Updated"
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert json_data["name"] == "Updated"
        client.close()

    def test_delete(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value=None):
            client.clients.delete(1)
        client.close()

    def test_activate(self):
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "One", "is_active": True}
        with patch.object(client, "_request", return_value=response_data):
            result = client.clients.activate(1)
            assert result.is_active is True
        client.close()

    def test_deactivate(self):
        client = self._make_client()
        response_data = {
            "id": 1,
            "client_id": "c1",
            "name": "One",
            "is_active": False,
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.clients.deactivate(1)
            assert result.is_active is False
        client.close()


# ============================================================
# TemplatesAPI tests
# ============================================================


class TestTemplatesAPI:
    """Tests for TemplatesAPI."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_list(self):
        client = self._make_client()
        response_data = {"items": [{"id": 1, "name": "T1"}], "total": 1}
        with patch.object(client, "_request", return_value=response_data):
            result = client.templates.list()
            assert result.total == 1
        client.close()

    def test_create_minimal(self):
        client = self._make_client()
        response_data = {"id": 1, "name": "New"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.templates.create(
                slug="new", name="New", http_template="http {}", https_template="https {}"
            )
            assert result.name == "New"
        client.close()

    def test_create_with_description(self):
        client = self._make_client()
        response_data = {"id": 1, "name": "Described"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.templates.create(
                slug="described",
                name="Described",
                http_template="http {}",
                https_template="https {}",
                description="A described template",
            )
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert json_data["description"] == "A described template"
        client.close()

    def test_get(self):
        client = self._make_client()
        response_data = {"id": 1, "name": "T1"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.templates.get(1)
            assert result.id == 1
        client.close()

    def test_update(self):
        client = self._make_client()
        response_data = {"id": 1, "name": "Updated"}
        with patch.object(client, "_request", return_value=response_data):
            result = client.templates.update(
                1,
                name="Updated",
                http_template="new http {}",
                https_template="new https {}",
                description="updated desc",
            )
            assert result.name == "Updated"
        client.close()

    def test_delete(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value=None):
            client.templates.delete(1)
        client.close()

    def test_set_default(self):
        client = self._make_client()
        response_data = {"id": 1, "name": "T1", "is_default": True}
        with patch.object(client, "_request", return_value=response_data):
            result = client.templates.set_default(1)
            assert result.is_default is True
        client.close()

    def test_validate(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={"valid": True}) as request:
            result = client.templates.validate(1, {"domain": "a.example.com"})
            assert result["valid"] is True
            request.assert_called_once_with(
                "POST",
                "/admin/templates/1/validate",
                json={"test_variables": {"domain": "a.example.com"}},
            )
        client.close()

    def test_reprovision(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={"domains_affected": 5}) as request:
            result = client.templates.reprovision(1, dry_run=True)
            assert result["domains_affected"] == 5
            request.assert_called_once_with(
                "POST",
                "/admin/templates/1/reprovision",
                json={"only_active": True, "dry_run": True},
            )
        client.close()


# ============================================================
# StatsAPI tests
# ============================================================


class TestStatsAPI:
    """Tests for StatsAPI."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_overview(self):
        client = self._make_client()
        response_data = {
            "domains": {
                "total": 10,
                "active": 8,
                "pending": 1,
                "failed": 1,
                "deleted": 0,
                "by_status": {},
                "created_last_24h": 0,
                "created_last_7d": 2,
                "created_last_30d": 5,
                "activated_last_24h": 0,
                "activated_last_7d": 1,
                "ssl_expiring_soon": 0,
                "ssl_expired": 0,
            },
            "clients": {"total": 3},
            "templates": {"total": 2},
        }
        with patch.object(client, "_request", return_value=response_data):
            result = client.stats.overview()
            assert result.domains.total == 10
        client.close()

    def test_top_clients(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value=[{"client_id": "c1", "count": 5}]):
            result = client.stats.top_clients(limit=5)
            assert len(result) == 1
        client.close()

    def test_recent_activity(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value=[{"action": "create"}]):
            result = client.stats.recent_activity(limit=10)
            assert len(result) == 1
        client.close()

    def test_dashboard(self):
        client = self._make_client()
        with patch.object(client, "_request", return_value={"summary": "ok"}):
            result = client.stats.dashboard()
            assert result["summary"] == "ok"
        client.close()


# ============================================================
# AsyncCustomDomainClient tests
# ============================================================


class TestAsyncCustomDomainClient:
    """Tests for AsyncCustomDomainClient."""

    @pytest.mark.asyncio
    async def test_init(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com/",
            access_token="token123",
            timeout=60,
        )
        assert client.base_url == "https://api.example.com"
        assert client.access_token == "token123"
        await client.close()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        async with AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        ) as client:
            assert isinstance(client, AsyncCustomDomainClient)

    @pytest.mark.asyncio
    async def test_request_success(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "ok"}

        with patch.object(client._http, "request", return_value=mock_response):
            result = await client._request("GET", "/test")
            assert result == {"data": "ok"}
        await client.close()

    @pytest.mark.asyncio
    async def test_request_204(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch.object(client._http, "request", return_value=mock_response):
            result = await client._request("DELETE", "/test")
            assert result is None
        await client.close()

    @pytest.mark.asyncio
    async def test_request_error(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "server error"}
        mock_response.text = "server error"

        with (
            patch.object(client._http, "request", return_value=mock_response),
            pytest.raises(CustomDomainError),
        ):
            await client._request("GET", "/test")
        await client.close()

    @pytest.mark.asyncio
    async def test_request_error_json_fails(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = Exception("not json")
        mock_response.text = "plain error"

        with (
            patch.object(client._http, "request", return_value=mock_response),
            pytest.raises(CustomDomainError),
        ):
            await client._request("GET", "/test")
        await client.close()

    @pytest.mark.asyncio
    async def test_list_domains(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {
            "items": [{"id": "d1", "domain": "a.com", "status": "active"}],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }
        with patch.object(client, "_request", return_value=response_data):
            result = await client.list_domains()
            assert result.total == 1
        await client.close()

    @pytest.mark.asyncio
    async def test_list_domains_with_filters(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {"items": [], "total": 0, "limit": 10, "offset": 5}
        with patch.object(client, "_request", return_value=response_data):
            await client.list_domains(
                status=DomainStatus.ACTIVE,
                owner_id="org_1",
            )
        await client.close()

    @pytest.mark.asyncio
    async def test_create_domain(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {
            "id": "d1",
            "domain": "new.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
        }
        with patch.object(client, "_request", return_value=response_data):
            result = await client.create_domain(
                domain="new.com",
                owner_id="org_1",
                owner_type="organization",
            )
            assert result.domain == "new.com"
        await client.close()

    @pytest.mark.asyncio
    async def test_create_domain_with_all_options(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {
            "id": "d1",
            "domain": "new.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
        }
        with patch.object(client, "_request", return_value=response_data):
            await client.create_domain(
                domain="new.com",
                owner_id="org_1",
                owner_type="organization",
                upstream_target="http://localhost",
                cname_target="apps.example.com",
                nginx_template_id=1,
                metadata={"k": "v"},
            )
        await client.close()

    @pytest.mark.asyncio
    async def test_get_domain(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data):
            result = await client.get_domain("d1")
            assert result.id == "d1"
        await client.close()

    @pytest.mark.asyncio
    async def test_delete_domain(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        with patch.object(client, "_request", return_value=None):
            await client.delete_domain("d1")
        await client.close()

    @pytest.mark.asyncio
    async def test_lookup_domain(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {
            "domain": "example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
            "client_id": "c1",
            "status": "active",
        }
        with patch.object(client, "_request", return_value=response_data):
            result = await client.lookup_domain("example.com")
            assert result.domain == "example.com"
        await client.close()

    @pytest.mark.asyncio
    async def test_get_domain_status(self):
        client = AsyncCustomDomainClient(
            base_url="https://api.example.com",
            access_token="token",
        )
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data):
            result = await client.get_domain_status("d1")
            assert result.status == DomainStatus.ACTIVE
        await client.close()


# ============================================================
# __init__.py import tests
# ============================================================


class TestClientInit:
    """Tests for custom_domain/client/__init__.py exports."""

    def test_all_exports(self):
        from custom_domain.client import __all__

        expected = [
            "AsyncCustomDomainClient",
            "AuthenticationError",
            "AuthorizationError",
            "AvailableTemplate",
            "Client",
            "ClientList",
            "ClientsAPI",
            "ConflictError",
            "CustomDomainClient",
            "CustomDomainError",
            "Domain",
            "DomainCreate",
            "DomainList",
            "DomainLookup",
            "DomainStatus",
            "DomainStatus_",
            "DomainsAPI",
            "NotFoundError",
            "OverviewStats",
            "SSEEvent",
            "StatsAPI",
            "Template",
            "TemplateList",
            "TemplatesAPI",
            "ValidationError",
            "WebhookEvent",
            "WebhookSignatureError",
            "construct_event",
            "verify_webhook_signature",
        ]
        assert sorted(__all__) == sorted(expected)

    def test_imports_from_init(self):
        """All __all__ items are importable from custom_domain.client."""
        from custom_domain import client as client_module

        for name in client_module.__all__:
            assert hasattr(client_module, name)


class TestUpdateMethodsNoneBranches:
    """Tests for update methods when optional params are None (false branches)."""

    def _make_client(self):
        return CustomDomainClient(base_url="https://api.example.com", access_token="token")

    def test_domains_update_no_optional_params(self):
        """DomainsAPI.update with no optional params sends empty data."""
        client = self._make_client()
        response_data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.domains.update("d1")
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert json_data == {}
        client.close()

    def test_clients_update_no_optional_params(self):
        """ClientsAPI.update with no optional params sends empty data."""
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "One"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.clients.update(1)
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert json_data == {}
        client.close()

    def test_templates_update_no_optional_params(self):
        """TemplatesAPI.update with no optional params sends empty data."""
        client = self._make_client()
        response_data = {"id": 1, "name": "T1"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.templates.update(1)
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert json_data == {}
        client.close()

    def test_domains_create_no_optional_params(self):
        """DomainsAPI.create with only required params."""
        client = self._make_client()
        response_data = {
            "id": "d1",
            "domain": "a.com",
            "status": "pending",
            "cname_target": "apps.example.com",
            "owner_id": "org_1",
            "owner_type": "organization",
        }
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.domains.create(domain="a.com", owner_id="org_1", owner_type="organization")
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert "upstream_target" not in json_data
            assert "cname_target" not in json_data
            assert "nginx_template_id" not in json_data
            assert "metadata" not in json_data
        client.close()

    def test_clients_create_no_optional_params(self):
        """ClientsAPI.create with only required params."""
        client = self._make_client()
        response_data = {"id": 1, "client_id": "c1", "name": "One"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.clients.create(client_id="c1", name="One")
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert "description" not in json_data
            assert "default_upstream_target" not in json_data
            assert "metadata" not in json_data
        client.close()

    def test_templates_create_no_description(self):
        """TemplatesAPI.create without description."""
        client = self._make_client()
        response_data = {"id": 1, "name": "T1"}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.templates.create(
                slug="t1", name="T1", http_template="http {}", https_template="https {}"
            )
            json_data = mock_req.call_args.kwargs.get("json", {})
            assert "description" not in json_data
        client.close()

    def test_async_create_domain_no_optional_params(self):
        """AsyncCustomDomainClient.create_domain with only required params."""

        async def _test():
            client = AsyncCustomDomainClient(
                base_url="https://api.example.com", access_token="token"
            )
            response_data = {
                "id": "d1",
                "domain": "a.com",
                "status": "pending",
                "cname_target": "apps.example.com",
                "owner_id": "org_1",
                "owner_type": "organization",
            }
            with patch.object(client, "_request", return_value=response_data) as mock_req:
                await client.create_domain(
                    domain="a.com", owner_id="org_1", owner_type="organization"
                )
                json_data = mock_req.call_args.kwargs.get("json", {})
                assert "upstream_target" not in json_data
            await client.close()

        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_test())

    def test_async_list_domains_no_filters(self):
        """AsyncCustomDomainClient.list_domains without status/owner_id."""

        async def _test():
            client = AsyncCustomDomainClient(
                base_url="https://api.example.com", access_token="token"
            )
            response_data = {
                "items": [],
                "total": 0,
                "limit": 20,
                "offset": 0,
            }
            with patch.object(client, "_request", return_value=response_data) as mock_req:
                await client.list_domains()
                params = mock_req.call_args.kwargs.get("params", {})
                assert "status_filter" not in params
                assert "owner_id" not in params
            await client.close()

        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(_test())

    def test_domains_list_no_filters(self):
        """DomainsAPI.list without status/owner_id."""
        client = self._make_client()
        response_data = {"items": [], "total": 0, "limit": 20, "offset": 0}
        with patch.object(client, "_request", return_value=response_data) as mock_req:
            client.domains.list()
            params = mock_req.call_args.kwargs.get("params", {})
            assert "status_filter" not in params
            assert "owner_id" not in params
        client.close()


class TestDomainStatusEnum:
    """Tests for DomainStatus enum values."""

    def test_all_values(self):
        assert DomainStatus.PENDING == "pending"
        assert DomainStatus.DNS_VERIFYING == "dns_verifying"
        assert DomainStatus.DNS_VERIFIED == "dns_verified"
        assert DomainStatus.SSL_PROVISIONING == "ssl_provisioning"
        assert DomainStatus.ACTIVE == "active"
        assert DomainStatus.FAILED == "failed"
        assert DomainStatus.SUSPENDED == "suspended"
        assert DomainStatus.EXPIRED == "expired"
        assert DomainStatus.DEPROVISIONING == "deprovisioning"

    def test_every_server_status_is_known(self):
        """The client knows every status the service can report."""
        from custom_domain.models.enums import DomainStatus as ServerStatus

        assert {s.value for s in DomainStatus} == {s.value for s in ServerStatus}


class TestAsynchronousDeletion:
    """Deleting reports the worker-driven deprovisioning."""

    def test_sync_delete_returns_the_answer(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="t")
        answer = {"id": "d1", "status": "deprovisioning", "message": "Deprovisioning started"}
        with patch.object(client, "_request", return_value=answer) as mock_req:
            assert client.domains.delete("d1") == answer
        mock_req.assert_called_once_with("DELETE", "/domains/d1")
        client.close()

    @pytest.mark.asyncio
    async def test_async_delete_returns_the_answer(self):
        client = AsyncCustomDomainClient(base_url="https://api.example.com", access_token="t")
        answer = {"id": "d1", "status": "deprovisioning", "message": "Deprovisioning started"}
        with patch.object(client, "_request", return_value=answer):
            assert await client.delete_domain("d1") == answer
        await client.close()

    def test_a_202_answer_is_returned_as_json(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="t")
        response = MagicMock(status_code=202)
        response.json.return_value = {"status": "deprovisioning"}
        with patch.object(client._http, "request", return_value=response):
            assert client._request("DELETE", "/domains/d1") == {"status": "deprovisioning"}
        client.close()


class TestAsyncClientCoversTheDomainLifecycle:
    """The async client exposes the same domain operations as the sync one."""

    @staticmethod
    def make():
        return AsyncCustomDomainClient(base_url="https://api.example.com", access_token="t")

    @pytest.mark.asyncio
    async def test_update_domain(self):
        client = self.make()
        data = {"id": "d1", "domain": "a.com", "status": "active"}
        with patch.object(client, "_request", return_value=data) as mock_req:
            result = await client.update_domain(
                "d1", upstream_target="/run/x.sock", nginx_template_id=2, metadata={"k": 1}
            )
        assert result.id == "d1"
        mock_req.assert_called_once_with(
            "PUT",
            "/domains/d1",
            json={"upstream_target": "/run/x.sock", "nginx_template_id": 2, "metadata": {"k": 1}},
        )
        await client.close()

    @pytest.mark.asyncio
    async def test_update_domain_only_sends_given_fields(self):
        client = self.make()
        with patch.object(
            client, "_request", return_value={"id": "d", "domain": "a", "status": "active"}
        ) as mock_req:
            await client.update_domain("d1", metadata={})
        assert mock_req.call_args.kwargs["json"] == {"metadata": {}}
        await client.close()

    @pytest.mark.asyncio
    async def test_verify_and_provision(self):
        client = self.make()
        answer = {"id": "d1", "status": "dns_verifying", "message": "ok"}
        with patch.object(client, "_request", return_value=answer) as mock_req:
            assert await client.verify_domain("d1") == answer
            assert await client.provision_domain("d1") == answer
        assert [c.args for c in mock_req.call_args_list] == [
            ("POST", "/domains/d1/verify"),
            ("POST", "/domains/d1/provision"),
        ]
        await client.close()

    @pytest.mark.asyncio
    async def test_event_history(self):
        client = self.make()
        data = {
            "events": [
                {"type": "completed", "message": "done", "timestamp": "2026-01-01T00:00:00+00:00"}
            ]
        }
        with patch.object(client, "_request", return_value=data) as mock_req:
            events = await client.get_event_history("d1", limit=5)
        assert len(events) == 1
        mock_req.assert_called_once_with("GET", "/domains/d1/events/history", params={"limit": 5})
        await client.close()


class TestAsyncErrorsAreTyped:
    """The async client raises the same typed errors as the sync client."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "error"),
        [
            (401, "AuthenticationError"),
            (403, "AuthorizationError"),
            (404, "NotFoundError"),
            (409, "ConflictError"),
            (400, "ValidationError"),
            (500, "CustomDomainError"),
        ],
    )
    async def test_status_maps_to_error(self, status, error):
        import custom_domain.client as sdk

        client = AsyncCustomDomainClient(base_url="https://api.example.com", access_token="t")
        response = MagicMock(status_code=status, text="boom")
        response.json.return_value = {"detail": "boom"}
        with (
            patch.object(client._http, "request", AsyncMock(return_value=response)),
            pytest.raises(getattr(sdk, error)) as exc_info,
        ):
            await client.get_domain("d1")
        assert exc_info.value.status_code == status
        await client.close()


class TestDomainStatusErrorKey:
    """The status endpoint reports its failure reason under the ``error`` key."""

    def test_error_key_is_used_as_error_message(self):
        """DomainStatus_ falls back to the ``error`` key sent by the status endpoint."""
        from custom_domain.client import DomainStatus_

        status = DomainStatus_.from_dict(
            {"id": "d1", "domain": "a.example.com", "status": "failed", "error": "No CNAME record"}
        )
        assert status.error_message == "No CNAME record"


class TestSSEEventFlatItems:
    """The history endpoint returns flat items instead of a payload object."""

    def test_flat_history_item(self):
        e = SSEEvent.from_dict(
            {
                "type": "step_completed",
                "step": "certbot",
                "message": "done",
                "timestamp": "2024-01-15T10:00:00+00:00",
            }
        )
        assert e.event_type == "step_completed"
        assert e.payload["step"] == "certbot"
        assert e.timestamp is not None


class TestTemplateOwnership:
    """The SDK knows about shared and client-owned templates."""

    def test_available_templates_are_listed(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="t")
        answer = {
            "items": [
                {
                    "id": 1,
                    "slug": "default",
                    "name": "Default",
                    "description": None,
                    "shared": True,
                },
                {"id": 2, "slug": "own", "name": "Own", "description": "d", "shared": False},
            ],
            "total": 2,
        }
        with patch.object(client, "_request", return_value=answer) as mock_req:
            templates = client.domains.list_available_templates()
        mock_req.assert_called_once_with("GET", "/templates")
        assert [(t.slug, t.shared) for t in templates] == [("default", True), ("own", False)]
        assert templates[1].description == "d"
        client.close()

    @pytest.mark.asyncio
    async def test_async_available_templates(self):
        client = AsyncCustomDomainClient(base_url="https://api.example.com", access_token="t")
        answer = {"items": [{"id": 1, "slug": "s", "name": "S", "shared": True}], "total": 1}
        with patch.object(client, "_request", return_value=answer):
            templates = await client.list_available_templates()
        assert templates[0].id == 1
        await client.close()

    def test_template_carries_slug_and_owner(self):
        from custom_domain.client import Template

        template = Template.from_dict({"id": 1, "name": "N", "slug": "n", "client_id": "tenant-a"})
        assert (template.slug, template.client_id) == ("n", "tenant-a")
        assert Template.from_dict({"id": 1, "name": "N"}).client_id is None

    def test_create_sends_the_slug_and_the_owner(self):
        client = CustomDomainClient(base_url="https://api.example.com", access_token="t")
        with patch.object(client, "_request", return_value={"id": 1, "name": "N"}) as mock_req:
            client.templates.create(
                slug="n", name="N", http_template="h", https_template="s", client_id="tenant-a"
            )
        assert mock_req.call_args.kwargs["json"] == {
            "slug": "n",
            "name": "N",
            "http_template": "h",
            "https_template": "s",
            "client_id": "tenant-a",
        }
        client.close()

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom Domain Service Client.

A full-featured Python client for the Custom Domain Service API.

Usage:
    from client import CustomDomainClient

    # Initialize client
    client = CustomDomainClient(
        base_url="https://custom-domain.example.com",
        access_token="your-oauth2-token",
    )

    # Create a domain
    domain = client.domains.create(
        domain="app.example.com",
        owner_id="org_123",
        owner_type="organization",
    )

    # Check status
    status = client.domains.get_status(domain.id)

    # Stream events (SSE)
    for event in client.domains.stream_events(domain.id):
        print(event)
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urljoin

import httpx


class DomainStatus(StrEnum):
    """Domain status enum."""

    PENDING = "pending"
    DNS_VERIFYING = "dns_verifying"
    DNS_VERIFIED = "dns_verified"
    SSL_PROVISIONING = "ssl_provisioning"
    ACTIVE = "active"
    FAILED = "failed"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    DEPROVISIONING = "deprovisioning"


@dataclass
class Domain:
    """Domain model."""

    id: str
    domain: str
    client_id: str
    owner_id: str
    owner_type: str
    upstream_target: str
    cname_target: str
    status: DomainStatus
    error_message: str | None = None
    dns_verified_at: datetime | None = None
    ssl_provisioned_at: datetime | None = None
    ssl_expires_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    metadata: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Domain:
        """Create Domain from API response."""
        return cls(
            id=data["id"],
            domain=data["domain"],
            client_id=data.get("client_id", ""),
            owner_id=data.get("owner_id", ""),
            owner_type=data.get("owner_type", ""),
            upstream_target=data.get("upstream_target", ""),
            cname_target=data.get("cname_target", ""),
            status=DomainStatus(data["status"]),
            error_message=data.get("error_message"),
            dns_verified_at=_parse_datetime(data.get("dns_verified_at")),
            ssl_provisioned_at=_parse_datetime(data.get("ssl_provisioned_at")),
            ssl_expires_at=_parse_datetime(data.get("ssl_expires_at")),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            deleted_at=_parse_datetime(data.get("deleted_at")),
            metadata=data.get("metadata"),
        )


@dataclass
class DomainCreate:
    """Domain creation response."""

    id: str
    domain: str
    status: DomainStatus
    cname_target: str
    owner_id: str
    owner_type: str
    created_at: datetime | None = None
    dns_instructions: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DomainCreate:
        """Create from API response."""
        return cls(
            id=data["id"],
            domain=data["domain"],
            status=DomainStatus(data["status"]),
            cname_target=data["cname_target"],
            owner_id=data["owner_id"],
            owner_type=data["owner_type"],
            created_at=_parse_datetime(data.get("created_at")),
            dns_instructions=data.get("dns_instructions"),
        )


@dataclass
class DomainStatus_:
    """Domain status response."""

    id: str
    domain: str
    status: DomainStatus
    error_message: str | None = None
    retry_count: int = 0
    last_check_at: datetime | None = None
    dns_verified_at: datetime | None = None
    ssl_provisioned_at: datetime | None = None
    ssl_expires_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DomainStatus_:
        """Create from API response."""
        return cls(
            id=data["id"],
            domain=data["domain"],
            status=DomainStatus(data["status"]),
            error_message=data.get("error_message") or data.get("error"),
            retry_count=data.get("retry_count", 0),
            last_check_at=_parse_datetime(data.get("last_check_at")),
            dns_verified_at=_parse_datetime(data.get("dns_verified_at")),
            ssl_provisioned_at=_parse_datetime(data.get("ssl_provisioned_at")),
            ssl_expires_at=_parse_datetime(data.get("ssl_expires_at")),
        )


@dataclass
class DomainLookup:
    """Domain lookup response."""

    domain: str
    owner_id: str
    owner_type: str
    client_id: str
    status: DomainStatus
    metadata: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> DomainLookup:
        """Create from API response."""
        return cls(
            domain=data["domain"],
            owner_id=data["owner_id"],
            owner_type=data["owner_type"],
            client_id=data["client_id"],
            status=DomainStatus(data["status"]),
            metadata=data.get("metadata"),
        )


@dataclass
class DomainList:
    """Paginated domain list."""

    items: list[Domain]
    total: int
    limit: int
    offset: int

    @classmethod
    def from_dict(cls, data: dict) -> DomainList:
        """Create from API response."""
        return cls(
            items=[Domain.from_dict(d) for d in data["items"]],
            total=data["total"],
            limit=data["limit"],
            offset=data["offset"],
        )


@dataclass
class Client:
    """Authorized client model."""

    id: int
    client_id: str
    name: str
    description: str | None = None
    default_upstream_target: str | None = None
    default_cname_target: str | None = None
    default_nginx_template_id: int | None = None
    max_domains: int | None = None
    is_active: bool = True
    domains_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict | None = None
    webhook_url: str | None = None
    has_webhook_secret: bool = False

    @classmethod
    def from_dict(cls, data: dict) -> Client:
        """Create from API response."""
        return cls(
            id=data["id"],
            client_id=data["client_id"],
            name=data["name"],
            description=data.get("description"),
            default_upstream_target=data.get("default_upstream_target"),
            default_cname_target=data.get("default_cname_target"),
            default_nginx_template_id=data.get("default_nginx_template_id"),
            max_domains=data.get("max_domains"),
            is_active=data.get("is_active", True),
            domains_count=data.get("domains_count", 0),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
            metadata=data.get("metadata"),
            webhook_url=data.get("webhook_url"),
            has_webhook_secret=data.get("has_webhook_secret", False),
        )


@dataclass
class ClientList:
    """Client list response."""

    items: list[Client]
    total: int

    @classmethod
    def from_dict(cls, data: dict) -> ClientList:
        """Create from API response."""
        return cls(
            items=[Client.from_dict(c) for c in data["items"]],
            total=data["total"],
        )


@dataclass
class Template:
    """Nginx template model."""

    id: int
    name: str
    slug: str | None = None
    client_id: str | None = None
    description: str | None = None
    http_template: str | None = None
    https_template: str | None = None
    is_default: bool = False
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> Template:
        """Create from API response."""
        return cls(
            id=data["id"],
            name=data["name"],
            slug=data.get("slug"),
            client_id=data.get("client_id"),
            description=data.get("description"),
            http_template=data.get("http_template"),
            https_template=data.get("https_template"),
            is_default=data.get("is_default", False),
            is_active=data.get("is_active", True),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )


@dataclass
class TemplateList:
    """Template list response."""

    items: list[Template]
    total: int

    @classmethod
    def from_dict(cls, data: dict) -> TemplateList:
        """Create from API response."""
        return cls(
            items=[Template.from_dict(t) for t in data["items"]],
            total=data["total"],
        )


@dataclass
class AvailableTemplate:
    """A template a client may put on its domains (no sources)."""

    id: int
    slug: str
    name: str
    shared: bool
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> AvailableTemplate:
        """Create from API response."""
        return cls(
            id=data["id"],
            slug=data["slug"],
            name=data["name"],
            shared=data["shared"],
            description=data.get("description"),
        )


@dataclass
class DomainStats:
    """Domain statistics."""

    total: int
    active: int
    pending: int
    failed: int
    deleted: int
    by_status: dict[str, int]
    created_last_24h: int
    created_last_7d: int
    created_last_30d: int
    activated_last_24h: int
    activated_last_7d: int
    ssl_expiring_soon: int
    ssl_expired: int

    @classmethod
    def from_dict(cls, data: dict) -> DomainStats:
        """Create from API response."""
        return cls(
            total=data["total"],
            active=data["active"],
            pending=data["pending"],
            failed=data["failed"],
            deleted=data["deleted"],
            by_status=data["by_status"],
            created_last_24h=data["created_last_24h"],
            created_last_7d=data["created_last_7d"],
            created_last_30d=data["created_last_30d"],
            activated_last_24h=data["activated_last_24h"],
            activated_last_7d=data["activated_last_7d"],
            ssl_expiring_soon=data["ssl_expiring_soon"],
            ssl_expired=data["ssl_expired"],
        )


@dataclass
class OverviewStats:
    """Overview statistics."""

    domains: DomainStats
    clients: dict
    templates: dict

    @classmethod
    def from_dict(cls, data: dict) -> OverviewStats:
        """Create from API response."""
        return cls(
            domains=DomainStats.from_dict(data["domains"]),
            clients=data["clients"],
            templates=data["templates"],
        )


@dataclass
class SSEEvent:
    """Server-Sent Event."""

    event_type: str
    payload: dict
    timestamp: datetime | None = None

    @classmethod
    def from_dict(cls, data: dict) -> SSEEvent:
        """Create from event data."""
        payload = data.get("payload")
        if payload is None:
            # The history endpoint returns flat items: {type, step, message, timestamp}.
            payload = {key: value for key, value in data.items() if key != "type"}
        return cls(
            event_type=data.get("type", "unknown"),
            payload=payload,
            timestamp=_parse_datetime(payload.get("timestamp")),
        )


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse ISO datetime string."""
    if not value:
        return None
    try:
        # Handle both Z suffix and +00:00
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class CustomDomainError(Exception):
    """Base exception for Custom Domain client."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        detail: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class AuthenticationError(CustomDomainError):
    """Authentication failed."""

    pass


class AuthorizationError(CustomDomainError):
    """Authorization failed."""

    pass


class NotFoundError(CustomDomainError):
    """Resource not found."""

    pass


class ConflictError(CustomDomainError):
    """Resource conflict."""

    pass


class ValidationError(CustomDomainError):
    """Validation error."""

    pass


def raise_for_api_error(response: httpx.Response) -> None:
    """Handle API error response."""
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text

    if response.status_code == 401:
        raise AuthenticationError(
            "Authentication failed",
            status_code=401,
            detail=detail,
        )
    elif response.status_code == 403:
        raise AuthorizationError(
            "Access denied",
            status_code=403,
            detail=detail,
        )
    elif response.status_code == 404:
        raise NotFoundError(
            "Resource not found",
            status_code=404,
            detail=detail,
        )
    elif response.status_code == 409:
        raise ConflictError(
            "Resource conflict",
            status_code=409,
            detail=detail,
        )
    elif response.status_code == 400:
        raise ValidationError(
            "Validation error",
            status_code=400,
            detail=detail,
        )
    else:
        raise CustomDomainError(
            f"API error: {detail}",
            status_code=response.status_code,
            detail=detail,
        )


class DomainsAPI:
    """Domains API client."""

    def __init__(self, client: CustomDomainClient):
        self._client = client

    def list(
        self,
        status: DomainStatus | None = None,
        owner_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> DomainList:
        """List domains."""
        params = {
            "limit": limit,
            "offset": offset,
            "include_deleted": include_deleted,
        }
        if status:
            params["status_filter"] = status.value
        if owner_id:
            params["owner_id"] = owner_id

        response = self._client._request("GET", "/domains", params=params)
        return DomainList.from_dict(response)

    def create(
        self,
        domain: str,
        owner_id: str,
        owner_type: str,
        upstream_target: str | None = None,
        cname_target: str | None = None,
        nginx_template_id: int | None = None,
        metadata: dict | None = None,
    ) -> DomainCreate:
        """Create a new domain."""
        data = {
            "domain": domain,
            "owner_id": owner_id,
            "owner_type": owner_type,
        }
        if upstream_target:
            data["upstream_target"] = upstream_target
        if cname_target:
            data["cname_target"] = cname_target
        if nginx_template_id:
            data["nginx_template_id"] = nginx_template_id
        if metadata:
            data["metadata"] = metadata

        response = self._client._request("POST", "/domains", json=data)
        return DomainCreate.from_dict(response)

    def get(self, domain_id: str) -> Domain:
        """Get domain by ID."""
        response = self._client._request("GET", f"/domains/{domain_id}")
        return Domain.from_dict(response)

    def update(
        self,
        domain_id: str,
        upstream_target: str | None = None,
        nginx_template_id: int | None = None,
        metadata: dict | None = None,
    ) -> Domain:
        """Update a domain."""
        data = {}
        if upstream_target is not None:
            data["upstream_target"] = upstream_target
        if nginx_template_id is not None:
            data["nginx_template_id"] = nginx_template_id
        if metadata is not None:
            data["metadata"] = metadata

        response = self._client._request("PUT", f"/domains/{domain_id}", json=data)
        return Domain.from_dict(response)

    def delete(self, domain_id: str) -> dict:
        """Start the deletion of a domain.

        Deletion is asynchronous: the answer reports the status ``deprovisioning``
        and a worker finishes the job. Poll :meth:`get` (or :meth:`get_status`)
        until it raises :class:`NotFoundError`.
        """
        return self._client._request("DELETE", f"/domains/{domain_id}")

    def lookup(self, domain_name: str) -> DomainLookup:
        """Lookup domain by name (only the caller's own domains are found)."""
        response = self._client._request("GET", f"/domains/lookup/{domain_name}")
        return DomainLookup.from_dict(response)

    def list_available_templates(self) -> list[AvailableTemplate]:
        """List the nginx templates this client may use for its domains."""
        response = self._client._request("GET", "/templates")
        return [AvailableTemplate.from_dict(t) for t in response["items"]]

    def verify(self, domain_id: str) -> dict:
        """Trigger DNS verification."""
        return self._client._request("POST", f"/domains/{domain_id}/verify")

    def provision(self, domain_id: str) -> dict:
        """Trigger SSL provisioning."""
        return self._client._request("POST", f"/domains/{domain_id}/provision")

    def get_status(self, domain_id: str) -> DomainStatus_:
        """Get domain status (polling)."""
        response = self._client._request("GET", f"/domains/{domain_id}/status")
        return DomainStatus_.from_dict(response)

    def get_event_history(self, domain_id: str, limit: int = 50) -> list[SSEEvent]:
        """Get event history."""
        response = self._client._request(
            "GET",
            f"/domains/{domain_id}/events/history",
            params={"limit": limit},
        )
        return [SSEEvent.from_dict(e) for e in response.get("events", [])]

    def stream_events(
        self,
        domain_id: str,
        timeout: float = 300,
    ) -> Generator[SSEEvent, None, None]:
        """Stream events via SSE."""
        url = urljoin(self._client.base_url, f"/api/v1/domains/{domain_id}/events")
        headers = {"Authorization": f"Bearer {self._client.access_token}"}

        with httpx.stream("GET", url, headers=headers, timeout=timeout) as response:
            response.raise_for_status()

            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    event_str, buffer = buffer.split("\n\n", 1)
                    event = self._parse_sse_event(event_str)
                    if event:
                        yield event

    def _parse_sse_event(self, event_str: str) -> SSEEvent | None:
        """Parse SSE event string."""
        data = None
        event_type = "message"

        for line in event_str.split("\n"):
            if line.startswith("data:"):
                data = line[5:].strip()
            elif line.startswith("event:"):
                event_type = line[6:].strip()

        if data:
            try:
                payload = json.loads(data)
                return SSEEvent(
                    event_type=payload.get("type", event_type),
                    payload=payload.get("payload", payload),
                    timestamp=_parse_datetime(payload.get("payload", {}).get("timestamp")),
                )
            except json.JSONDecodeError:
                pass

        return None

    def wait_for_active(
        self,
        domain_id: str,
        timeout: float = 600,
        poll_interval: float = 5,
        on_status_change: Callable[[DomainStatus_], None] | None = None,
    ) -> Domain:
        """Wait for domain to become active.

        Args:
            domain_id: Domain ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Polling interval in seconds
            on_status_change: Callback for status changes

        Returns:
            Domain when active

        Raises:
            CustomDomainError: If domain fails or times out
        """
        start_time = time.time()
        last_status = None

        while time.time() - start_time < timeout:
            status = self.get_status(domain_id)

            if status.status != last_status:
                last_status = status.status
                if on_status_change:
                    on_status_change(status)

            if status.status == DomainStatus.ACTIVE:
                return self.get(domain_id)

            if status.status == DomainStatus.FAILED:
                raise CustomDomainError(
                    f"Domain provisioning failed: {status.error_message}",
                    detail=status,
                )

            time.sleep(poll_interval)

        raise CustomDomainError(
            f"Timeout waiting for domain to become active (last status: {last_status})"
        )


class ClientsAPI:
    """Admin clients API."""

    def __init__(self, client: CustomDomainClient):
        self._client = client

    def list(self) -> ClientList:
        """List all clients."""
        response = self._client._request("GET", "/admin/clients")
        return ClientList.from_dict(response)

    def create(
        self,
        client_id: str,
        name: str,
        description: str | None = None,
        default_upstream_target: str | None = None,
        default_cname_target: str | None = None,
        default_nginx_template_id: int | None = None,
        max_domains: int | None = None,
        metadata: dict | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> Client:
        """Create a new client (``webhook_url`` needs ``webhook_secret``)."""
        data = {
            "client_id": client_id,
            "name": name,
        }
        if webhook_url:
            data["webhook_url"] = webhook_url
        if webhook_secret:
            data["webhook_secret"] = webhook_secret
        if description:
            data["description"] = description
        if default_upstream_target:
            data["default_upstream_target"] = default_upstream_target
        if default_cname_target:
            data["default_cname_target"] = default_cname_target
        if default_nginx_template_id:
            data["default_nginx_template_id"] = default_nginx_template_id
        if max_domains:
            data["max_domains"] = max_domains
        if metadata:
            data["metadata"] = metadata

        response = self._client._request("POST", "/admin/clients", json=data)
        return Client.from_dict(response)

    def get(self, client_id: int) -> Client:
        """Get client by ID."""
        response = self._client._request("GET", f"/admin/clients/{client_id}")
        return Client.from_dict(response)

    def update(
        self,
        client_id: int,
        name: str | None = None,
        description: str | None = None,
        default_upstream_target: str | None = None,
        default_cname_target: str | None = None,
        default_nginx_template_id: int | None = None,
        max_domains: int | None = None,
        metadata: dict | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> Client:
        """Update a client."""
        data = {}
        if webhook_url is not None:
            data["webhook_url"] = webhook_url
        if webhook_secret is not None:
            data["webhook_secret"] = webhook_secret
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if default_upstream_target is not None:
            data["default_upstream_target"] = default_upstream_target
        if default_cname_target is not None:
            data["default_cname_target"] = default_cname_target
        if default_nginx_template_id is not None:
            data["default_nginx_template_id"] = default_nginx_template_id
        if max_domains is not None:
            data["max_domains"] = max_domains
        if metadata is not None:
            data["metadata"] = metadata

        response = self._client._request("PUT", f"/admin/clients/{client_id}", json=data)
        return Client.from_dict(response)

    def delete(self, client_id: int) -> None:
        """Delete a client."""
        self._client._request("DELETE", f"/admin/clients/{client_id}")

    def activate(self, client_id: int) -> Client:
        """Activate a client."""
        response = self._client._request("POST", f"/admin/clients/{client_id}/activate")
        return Client.from_dict(response)

    def deactivate(self, client_id: int) -> Client:
        """Deactivate a client."""
        response = self._client._request("POST", f"/admin/clients/{client_id}/deactivate")
        return Client.from_dict(response)


class TemplatesAPI:
    """Admin templates API."""

    def __init__(self, client: CustomDomainClient):
        self._client = client

    def list(self) -> TemplateList:
        """List all templates."""
        response = self._client._request("GET", "/admin/templates")
        return TemplateList.from_dict(response)

    def create(
        self,
        slug: str,
        name: str,
        http_template: str,
        https_template: str,
        description: str | None = None,
        client_id: str | None = None,
    ) -> Template:
        """Create a new template, shared or owned by ``client_id``."""
        data = {
            "slug": slug,
            "name": name,
            "http_template": http_template,
            "https_template": https_template,
        }
        if description:
            data["description"] = description
        if client_id:
            data["client_id"] = client_id

        response = self._client._request("POST", "/admin/templates", json=data)
        return Template.from_dict(response)

    def get(self, template_id: int) -> Template:
        """Get template by ID."""
        response = self._client._request("GET", f"/admin/templates/{template_id}")
        return Template.from_dict(response)

    def update(
        self,
        template_id: int,
        name: str | None = None,
        http_template: str | None = None,
        https_template: str | None = None,
        description: str | None = None,
    ) -> Template:
        """Update a template."""
        data = {}
        if name is not None:
            data["name"] = name
        if http_template is not None:
            data["http_template"] = http_template
        if https_template is not None:
            data["https_template"] = https_template
        if description is not None:
            data["description"] = description

        response = self._client._request("PUT", f"/admin/templates/{template_id}", json=data)
        return Template.from_dict(response)

    def delete(self, template_id: int) -> None:
        """Delete a template."""
        self._client._request("DELETE", f"/admin/templates/{template_id}")

    def set_default(self, template_id: int) -> Template:
        """Set template as default."""
        response = self._client._request("POST", f"/admin/templates/{template_id}/set-default")
        return Template.from_dict(response)

    def validate(self, template_id: int, test_variables: dict | None = None) -> dict:
        """Render a template with test variables and check its nginx syntax."""
        return self._client._request(
            "POST",
            f"/admin/templates/{template_id}/validate",
            json={"test_variables": test_variables or {}},
        )

    def reprovision(
        self,
        template_id: int,
        only_active: bool = True,
        dry_run: bool = False,
    ) -> dict:
        """Reprovision the domains using this template."""
        return self._client._request(
            "POST",
            f"/admin/templates/{template_id}/reprovision",
            json={"only_active": only_active, "dry_run": dry_run},
        )


class StatsAPI:
    """Admin statistics API."""

    def __init__(self, client: CustomDomainClient):
        self._client = client

    def overview(self) -> OverviewStats:
        """Get overview statistics."""
        response = self._client._request("GET", "/admin/stats/overview")
        return OverviewStats.from_dict(response)

    def top_clients(self, limit: int = 10) -> list[dict]:
        """Get top clients by domain count."""
        return self._client._request(
            "GET",
            "/admin/stats/top-clients",
            params={"limit": limit},
        )

    def recent_activity(self, limit: int = 20) -> list[dict]:
        """Get recent domain activity."""
        return self._client._request(
            "GET",
            "/admin/stats/recent-activity",
            params={"limit": limit},
        )

    def dashboard(self) -> dict:
        """Get complete dashboard data."""
        return self._client._request("GET", "/admin/stats/dashboard")


class CustomDomainClient:
    """Custom Domain Service client.

    Args:
        base_url: Base URL of the Custom Domain Service
        access_token: OAuth2 access token
        timeout: Request timeout in seconds
        token_refresher: Optional callable to refresh expired tokens

    Example:
        client = CustomDomainClient(
            base_url="https://custom-domain.example.com",
            access_token="your-token",
        )

        # Create a domain
        domain = client.domains.create(
            domain="app.example.com",
            owner_id="org_123",
            owner_type="organization",
        )

        # Wait for it to become active
        active_domain = client.domains.wait_for_active(domain.id)
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout: float = 30,
        token_refresher: Callable[[], str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.token_refresher = token_refresher

        self._http = httpx.Client(timeout=timeout)

        # API namespaces
        self.domains = DomainsAPI(self)
        self.clients = ClientsAPI(self)
        self.templates = TemplatesAPI(self)
        self.stats = StatsAPI(self)

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
        retry_on_401: bool = True,
    ) -> Any:
        """Make an API request."""
        url = urljoin(self.base_url, f"/api/v1{path}")
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = self._http.request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
        )

        # Handle 401 with token refresh
        if response.status_code == 401 and retry_on_401 and self.token_refresher:
            self.access_token = self.token_refresher()
            return self._request(method, path, params, json, retry_on_401=False)

        # Handle errors
        if response.status_code >= 400:
            self._handle_error(response)

        # Return empty for 204
        if response.status_code == 204:
            return None

        return response.json()

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle API error response."""
        raise_for_api_error(response)

    def health(self) -> dict:
        """Check service health."""
        response = self._http.get(urljoin(self.base_url, "/health"))
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()

    def __enter__(self) -> CustomDomainClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()


# Async client for use with asyncio
class AsyncCustomDomainClient:
    """Async Custom Domain Service client.

    Example:
        async with AsyncCustomDomainClient(
            base_url="https://custom-domain.example.com",
            access_token="your-token",
        ) as client:
            domain = await client.create_domain(
                domain="app.example.com",
                owner_id="org_123",
                owner_type="organization",
            )
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout: float = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self._http = httpx.AsyncClient(timeout=timeout)

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        """Make an async API request."""
        url = urljoin(self.base_url, f"/api/v1{path}")
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = await self._http.request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
        )

        if response.status_code >= 400:
            raise_for_api_error(response)

        if response.status_code == 204:
            return None

        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncCustomDomainClient:
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # Domain methods
    async def list_domains(
        self,
        status: DomainStatus | None = None,
        owner_id: str | None = None,
        include_deleted: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> DomainList:
        """List domains."""
        params = {
            "limit": limit,
            "offset": offset,
            "include_deleted": include_deleted,
        }
        if status:
            params["status_filter"] = status.value
        if owner_id:
            params["owner_id"] = owner_id

        response = await self._request("GET", "/domains", params=params)
        return DomainList.from_dict(response)

    async def create_domain(
        self,
        domain: str,
        owner_id: str,
        owner_type: str,
        upstream_target: str | None = None,
        cname_target: str | None = None,
        nginx_template_id: int | None = None,
        metadata: dict | None = None,
    ) -> DomainCreate:
        """Create a new domain."""
        data = {
            "domain": domain,
            "owner_id": owner_id,
            "owner_type": owner_type,
        }
        if upstream_target:
            data["upstream_target"] = upstream_target
        if cname_target:
            data["cname_target"] = cname_target
        if nginx_template_id:
            data["nginx_template_id"] = nginx_template_id
        if metadata:
            data["metadata"] = metadata

        response = await self._request("POST", "/domains", json=data)
        return DomainCreate.from_dict(response)

    async def get_domain(self, domain_id: str) -> Domain:
        """Get domain by ID."""
        response = await self._request("GET", f"/domains/{domain_id}")
        return Domain.from_dict(response)

    async def update_domain(
        self,
        domain_id: str,
        upstream_target: str | None = None,
        nginx_template_id: int | None = None,
        metadata: dict | None = None,
    ) -> Domain:
        """Update a domain."""
        data = {}
        if upstream_target is not None:
            data["upstream_target"] = upstream_target
        if nginx_template_id is not None:
            data["nginx_template_id"] = nginx_template_id
        if metadata is not None:
            data["metadata"] = metadata

        response = await self._request("PUT", f"/domains/{domain_id}", json=data)
        return Domain.from_dict(response)

    async def delete_domain(self, domain_id: str) -> dict:
        """Start the deletion of a domain (asynchronous, see ``DomainsAPI.delete``)."""
        return await self._request("DELETE", f"/domains/{domain_id}")

    async def verify_domain(self, domain_id: str) -> dict:
        """Trigger DNS verification."""
        return await self._request("POST", f"/domains/{domain_id}/verify")

    async def provision_domain(self, domain_id: str) -> dict:
        """Trigger SSL provisioning."""
        return await self._request("POST", f"/domains/{domain_id}/provision")

    async def lookup_domain(self, domain_name: str) -> DomainLookup:
        """Lookup domain by name."""
        response = await self._request("GET", f"/domains/lookup/{domain_name}")
        return DomainLookup.from_dict(response)

    async def list_available_templates(self) -> list[AvailableTemplate]:
        """List the nginx templates this client may use for its domains."""
        response = await self._request("GET", "/templates")
        return [AvailableTemplate.from_dict(t) for t in response["items"]]

    async def get_domain_status(self, domain_id: str) -> DomainStatus_:
        """Get domain status."""
        response = await self._request("GET", f"/domains/{domain_id}/status")
        return DomainStatus_.from_dict(response)

    async def get_event_history(self, domain_id: str, limit: int = 50) -> list[SSEEvent]:
        """Get event history."""
        response = await self._request(
            "GET", f"/domains/{domain_id}/events/history", params={"limit": limit}
        )
        return [SSEEvent.from_dict(e) for e in response.get("events", [])]


if __name__ == "__main__":
    # Example usage
    import os

    BASE_URL = os.environ["CUSTOM_DOMAIN_URL"]
    TOKEN = os.environ["CUSTOM_DOMAIN_TOKEN"]

    with CustomDomainClient(base_url=BASE_URL, access_token=TOKEN) as client:
        # Check health
        print("Health:", client.health())

        # List domains
        domains = client.domains.list()
        print(f"Found {domains.total} domains")

        for d in domains.items:
            print(f"  - {d.domain} ({d.status.value})")

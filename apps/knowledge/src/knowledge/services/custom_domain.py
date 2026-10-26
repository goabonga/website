# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Custom domains of the Enterprise workspaces.

The application keeps what is its own business: which plan may have a custom domain,
the format of the name, and the table that maps a host name to a workspace (see the
tenant middleware). Everything else is delegated to the platform's custom-domain service:
DNS verification, certificate, web server configuration, renewal and removal.

This module holds the format validation, the mapping of the statuses of the service to
the ones of the application, and :class:`CustomDomainClient`, a thin client of the HTTP
API of the service (register, read, restart the verification, delete, list). The service
tells the application about status changes with signed webhooks (see
:mod:`knowledge.routes.custom_domain_webhooks`) and the reconciliation task polls it as a
safety net.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from knowledge.config import get_settings
from knowledge.logging import get_logger
from knowledge.models.enums import CustomDomainStatus
from knowledge.models.organization import Organization
from knowledge.services.service_auth import (
    ServiceAuthError,
    TokenCache,
    credentials_for,
)

logger = get_logger(__name__)

DOMAIN_REGEX = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63})*\.[A-Za-z]{2,}$")
MAX_DOMAIN_LENGTH = 253
RESERVED_DOMAINS = frozenset({"localhost", "127.0.0.1", "0.0.0.0"})  # nosec B104

DOMAINS_PATH = "/api/v1/domains"
READ_SCOPE = "custom-domain:read"
WRITE_SCOPE = "custom-domain:write"
OWNER_TYPE = "organization"
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Statuses of the service that the application does not distinguish
_FAILED_STATUSES = {"failed", "suspended", "expired"}


def validate_domain(domain: str) -> tuple[bool, str]:
    """Validate domain format.

    Args:
        domain: The domain to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not domain:
        return False, "Domain is required"

    domain = domain.lower().strip()

    if len(domain) > MAX_DOMAIN_LENGTH:
        return False, f"Domain is too long (max {MAX_DOMAIN_LENGTH} characters)"

    if not DOMAIN_REGEX.match(domain):
        return False, "Invalid domain format"

    # Local names and addresses can never be customer domains
    if domain in RESERVED_DOMAINS or domain.endswith(".local"):
        return False, "Reserved domain not allowed"

    return True, ""


def map_status(service_status: str | None) -> CustomDomainStatus | None:
    """Translate a status of the custom-domain service to the application's status.

    The service also knows ``suspended``, ``expired`` (both shown as ``failed``, with the
    reason as error) and ``deprovisioning`` (``None``: the domain is being removed).
    """
    if service_status is None or service_status == "deprovisioning":
        return None
    if service_status in _FAILED_STATUSES:
        return CustomDomainStatus.FAILED
    try:
        return CustomDomainStatus(service_status)
    except ValueError:
        logger.warning("Unknown custom domain status: %s", service_status)
        return None


_STATUS_REASONS = {
    "suspended": "The domain was suspended by the custom domain service",
    "expired": "The certificate of the domain has expired",
}
MAX_ERROR_LENGTH = 500


def apply_status(
    organization: Organization,
    service_status: str | None,
    error: str | None = None,
    when: datetime | None = None,
) -> bool:
    """Copy a status of the service into the ``custom_domain_*`` columns of a workspace.

    The webhooks and the reconciliation task both end here, so that the two ways of learning
    a status give the same result. Applying the same status twice changes nothing but
    ``custom_domain_checked_at``.

    Args:
        organization: The workspace that owns the domain.
        service_status: Status as the service reports it.
        error: Reason of a failure, when the service gave one.
        when: Moment the status is known from (default: now).

    Returns:
        ``False`` when the status says nothing to record (the domain is being removed).
    """
    status = map_status(service_status)
    if status is None:
        return False

    moment = when or datetime.now(UTC)
    organization.custom_domain_status = status
    organization.custom_domain_checked_at = moment

    if status == CustomDomainStatus.FAILED:
        reason = error or _STATUS_REASONS.get(service_status or "", "Provisioning failed")
        organization.custom_domain_error = reason[:MAX_ERROR_LENGTH]
    else:
        organization.custom_domain_error = None

    if status in (CustomDomainStatus.PENDING, CustomDomainStatus.DNS_VERIFYING):
        organization.custom_domain_verified_at = None
        organization.custom_domain_ssl_at = None
    if status in (
        CustomDomainStatus.DNS_VERIFIED,
        CustomDomainStatus.SSL_PROVISIONING,
        CustomDomainStatus.ACTIVE,
    ):
        organization.custom_domain_verified_at = organization.custom_domain_verified_at or moment
    if status == CustomDomainStatus.ACTIVE:
        organization.custom_domain_ssl_at = organization.custom_domain_ssl_at or moment
    return True


def clear_domain(organization: Organization) -> None:
    """Forget the custom domain of a workspace (it no longer resolves to it)."""
    organization.custom_domain = None
    organization.custom_domain_status = None
    organization.custom_domain_error = None
    organization.custom_domain_verified_at = None
    organization.custom_domain_ssl_at = None
    organization.custom_domain_checked_at = None
    organization.custom_domain_service_id = None
    organization.custom_domain_cname_target = None


class CustomDomainError(Exception):
    """A call to the custom-domain service failed.

    ``status_code`` is the HTTP status of the answer (``None`` when there was none) and
    ``retryable`` tells whether trying again can work.
    """

    def __init__(self, detail: str, status_code: int | None = None, retryable: bool = False):
        self.detail = detail
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(detail)


@dataclass(frozen=True)
class RegisteredDomain:
    """A domain just registered in the service."""

    id: str
    domain: str
    status: str
    cname_target: str
    dns_instructions: str = ""


@dataclass(frozen=True)
class DomainDetails:
    """A domain as the service reports it."""

    id: str
    domain: str
    status: str
    error_message: str | None = None
    dns_verified_at: str | None = None
    ssl_provisioned_at: str | None = None
    cname_target: str | None = None


class CustomDomainClient:
    """Thin client of the custom-domain service, over HTTP or a Unix socket.

    The calls are asynchronous and use a short-lived connection each, so that the client
    can be used from the web routes and from the Celery tasks (each task has its own
    event loop).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.custom_domain_service_url.rstrip("/")
        self.socket_path = settings.custom_domain_service_socket_path
        self.timeout = settings.service_timeout
        self._tokens = TokenCache()

    @property
    def is_configured(self) -> bool:
        """Whether a URL or a socket is configured."""
        return bool(self.url) or bool(self.socket_path)

    @property
    def base_url(self) -> str:
        """Base URL of the requests; the host is only a placeholder with a Unix socket."""
        return "http://localhost" if self.socket_path else self.url

    def _http_client(self) -> httpx.AsyncClient:
        if self.socket_path:
            transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
            return httpx.AsyncClient(transport=transport, timeout=self.timeout)
        return httpx.AsyncClient(timeout=self.timeout)

    async def _request(
        self, method: str, path: str, scope: str, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        if not self.is_configured:
            raise CustomDomainError(
                "CUSTOM_DOMAIN_SERVICE_URL or CUSTOM_DOMAIN_SERVICE_SOCKET_PATH is not configured"
            )
        response = await self._send(method, path, scope, json)
        if response.status_code == 401:
            # The token was revoked or expired early: ask for a new one, once
            self._tokens.clear()
            response = await self._send(method, path, scope, json)
        return response

    async def _send(
        self, method: str, path: str, scope: str, json: dict[str, Any] | None
    ) -> httpx.Response:
        try:
            token = await self._tokens.aget(credentials_for("custom_domain"), scope)
        except ServiceAuthError as error:
            raise CustomDomainError(str(error), retryable=error.retryable) from error

        try:
            async with self._http_client() as client:
                return await client.request(
                    method,
                    f"{self.base_url}{path}",
                    json=json,
                    headers={"Authorization": f"Bearer {token}"},
                )
        except httpx.RequestError as error:
            raise CustomDomainError(
                f"Custom domain service request failed: {error}", retryable=True
            ) from error

    @staticmethod
    def _check(response: httpx.Response, expected: tuple[int, ...]) -> dict[str, Any]:
        if response.status_code not in expected:
            detail = _detail(response)
            raise CustomDomainError(
                detail,
                status_code=response.status_code,
                retryable=response.status_code in RETRYABLE_STATUS_CODES,
            )
        try:
            body = response.json()
        except ValueError as error:
            raise CustomDomainError("Unexpected answer of the custom domain service") from error
        return body if isinstance(body, dict) else {}

    async def register(
        self, domain: str, owner_id: str, metadata: dict[str, Any] | None = None
    ) -> RegisteredDomain:
        """Register a domain for a workspace; the service starts verifying the DNS.

        The upstream and the CNAME target are those of the registration of this
        application's client in the service.

        Raises:
            CustomDomainError: ``409`` the name is registered (by another application or
                workspace), ``403`` the client is not authorized or its quota is reached,
                ``400`` the service refuses the name or has no upstream or CNAME for us.
        """
        body: dict[str, Any] = {"domain": domain, "owner_id": owner_id, "owner_type": OWNER_TYPE}
        if metadata:
            body["metadata"] = metadata
        data = self._check(await self._request("POST", DOMAINS_PATH, WRITE_SCOPE, body), (201,))
        try:
            return RegisteredDomain(
                id=str(data["id"]),
                domain=data.get("domain", domain),
                status=data.get("status", "pending"),
                cname_target=data.get("cname_target", ""),
                dns_instructions=data.get("dns_instructions", ""),
            )
        except KeyError as error:
            raise CustomDomainError("Unexpected answer of the custom domain service") from error

    async def get(self, domain_id: str) -> DomainDetails | None:
        """Read a domain; ``None`` when the service does not know it (any more)."""
        response = await self._request("GET", f"{DOMAINS_PATH}/{domain_id}", READ_SCOPE)
        if response.status_code == 404:
            return None
        data = self._check(response, (200,))
        return DomainDetails(
            id=str(data.get("id", domain_id)),
            domain=data.get("domain", ""),
            status=data.get("status", ""),
            error_message=data.get("error_message"),
            dns_verified_at=data.get("dns_verified_at"),
            ssl_provisioned_at=data.get("ssl_provisioned_at"),
            cname_target=data.get("cname_target"),
        )

    async def verify(self, domain_id: str) -> str:
        """Restart the DNS verification of a domain; return the new status.

        Raises:
            CustomDomainError: ``400`` when the domain is in a status that does not allow it,
                ``404`` when the service does not know it.
        """
        data = self._check(
            await self._request("POST", f"{DOMAINS_PATH}/{domain_id}/verify", WRITE_SCOPE),
            (200,),
        )
        return data.get("status", "")

    async def delete(self, domain_id: str) -> bool:
        """Ask the service to remove a domain (asynchronous on its side).

        Returns:
            ``True`` when the removal was started, ``False`` when the service did not know
            the domain (it is gone already).
        """
        response = await self._request("DELETE", f"{DOMAINS_PATH}/{domain_id}", WRITE_SCOPE)
        if response.status_code == 404:
            return False
        self._check(response, (200, 202))
        return True

    async def list_domains(
        self, owner_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List the domains of this application (the first ``limit``), of one workspace if given."""
        path = f"{DOMAINS_PATH}?limit={limit}"
        if owner_id:
            path += f"&owner_id={owner_id}"
        data = self._check(await self._request("GET", path, READ_SCOPE), (200,))
        return list(data.get("items", []))


def _detail(response: httpx.Response) -> str:
    """Extract the explanation of an error answer."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return str(detail)
    return f"Custom domain service answered {response.status_code}"


_client: CustomDomainClient | None = None


def get_custom_domain_client() -> CustomDomainClient:
    """Get or create the custom-domain client singleton."""
    global _client
    if _client is None:
        _client = CustomDomainClient()
    return _client

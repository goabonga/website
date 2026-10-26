# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Async HTTP client for Mailler API."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from internal.config import settings

logger = logging.getLogger(__name__)


class MaillerAPIError(Exception):
    """Exception for Mailler API errors with detail message."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class MaillerClient:
    """Async HTTP client for Mailler API."""

    def __init__(self) -> None:
        self._socket_path = settings.mailler_socket_path or ""
        # For socket connections, use http://localhost as base URL (routing via socket)
        if self._socket_path:
            self._base_url = "http://localhost"
        else:
            self._base_url = (
                settings.mailler_api_url.rstrip("/") if settings.mailler_api_url else ""
            )
        self._client_id = settings.oauth2_client_id
        self._client_secret = settings.oauth2_client_secret
        self._issuer = settings.oauth2_issuer.rstrip("/") if settings.oauth2_issuer else ""
        self._tokens: dict[str, tuple[str, datetime]] = {}

    @staticmethod
    def _with_admin(scope: str) -> str:
        """Add the administration scope of the mailler service (``MAILLER_ADMIN_SCOPE``).

        The service keeps each client's emails, templates, contacts, groups and campaigns apart;
        only a token that carries its administration scope sees all of them and may manage the
        client registry. An empty setting leaves the scope alone.
        """
        return " ".join(
            dict.fromkeys(name for name in (scope, settings.mailler_admin_scope) if name)
        )

    async def _get_access_token(self, scope: str = "mailler:read") -> str:
        """Get access token using client credentials flow."""
        if scope in self._tokens:
            token, expires_at = self._tokens[scope]
            if datetime.now(UTC) < expires_at - timedelta(seconds=30):
                return token

        if not self._issuer:
            raise ValueError("oauth2_issuer not configured")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._issuer}/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": scope,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = data["access_token"]
        expires_in = data.get("expires_in", 3600)
        expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
        self._tokens[scope] = (access_token, expires_at)
        return access_token

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        scope: str = "mailler:read",
    ) -> Any:
        """Make an authenticated request to the Mailler API."""
        if not self._base_url:
            logger.warning("mailler_api_url not configured")
            return {}

        try:
            token = await self._get_access_token(scope=self._with_admin(scope))
        except Exception as e:
            logger.error("Failed to get access token for Mailler API: %s", e)
            raise

        # Use Unix socket transport if configured
        transport = None
        if self._socket_path:
            transport = httpx.AsyncHTTPTransport(uds=self._socket_path)

        async with httpx.AsyncClient(
            timeout=settings.mailler_timeout, transport=transport
        ) as client:
            response = await client.request(
                method,
                f"{self._base_url}{endpoint}",
                params=params,
                json=json_data,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            # Handle 204 No Content responses (e.g., DELETE)
            if response.status_code == 204 or not response.content:
                return {}
            return response.json()

    async def get_providers(self) -> list[str]:
        """Get list of available email providers.

        Returns:
            List of provider names (e.g., ["brevo", "sendgrid", "ses"])
        """
        try:
            data = await self._request(
                "GET",
                "/api/v1/providers",
                scope="mailler:read",
            )
            if not data:
                return []
            return data.get("providers", [])
        except Exception as e:
            logger.exception("Failed to get providers from Mailler API: %s", e)
            return []

    async def get_stats(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        provider: str | None = None,
    ) -> dict[str, Any]:
        """Get email sending statistics.

        Args:
            start_date: Optional start date (YYYY-MM-DD format, defaults to 30 days ago)
            end_date: Optional end date (YYYY-MM-DD format, defaults to today)
            provider: Optional provider filter

        Returns:
            Statistics with totals, by_provider, and by_date breakdowns
        """
        try:
            params: dict[str, Any] = {}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            if provider:
                params["provider"] = provider

            data = await self._request(
                "GET",
                "/api/v1/stats",
                params=params if params else None,
                scope="mailler:stats",
            )
            if not data:
                return {}
            return data
        except Exception as e:
            logger.exception("Failed to get stats from Mailler API: %s", e)
            return {}

    async def get_emails(
        self,
        page: int = 1,
        page_size: int = 20,
        provider: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Get paginated list of emails.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page (max 100)
            provider: Optional provider filter
            status: Optional status filter

        Returns:
            Paginated email list with items, total, page, page_size, pages
        """
        try:
            params: dict[str, Any] = {
                "page": page,
                "page_size": page_size,
            }
            if provider:
                params["provider"] = provider
            if status:
                params["status"] = status

            data = await self._request(
                "GET",
                "/api/v1/emails",
                params=params,
                scope="mailler:read",
            )
            if not data:
                return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 1}
            return data
        except Exception as e:
            logger.exception("Failed to get emails from Mailler API: %s", e)
            return {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 1}

    async def get_email(self, email_id: str) -> dict[str, Any] | None:
        """Get email details by ID.

        Args:
            email_id: Email UUID

        Returns:
            Email details or None if not found
        """
        try:
            data = await self._request(
                "GET",
                f"/api/v1/emails/{email_id}",
                scope="mailler:read",
            )
            return data if data else None
        except Exception as e:
            logger.exception("Failed to get email from Mailler API: %s", e)
            return None

    # ==================== Templates ====================

    async def get_templates(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get paginated list of email templates."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if status:
                params["status"] = status
            if search:
                params["search"] = search
            data = await self._request("GET", "/api/v1/templates", params=params)
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get templates: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def get_template(self, template_id: int) -> dict[str, Any] | None:
        """Get template by ID."""
        try:
            data = await self._request("GET", f"/api/v1/templates/{template_id}")
            return data if data else None
        except Exception as e:
            logger.exception("Failed to get template: %s", e)
            return None

    async def create_template(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new template."""
        try:
            return await self._request(
                "POST", "/api/v1/templates", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to create template: %s", e)
            return None

    async def update_template(
        self, template_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a template."""
        try:
            return await self._request(
                "PUT", f"/api/v1/templates/{template_id}", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to update template: %s", e)
            return None

    async def delete_template(self, template_id: int) -> bool:
        """Delete a template."""
        try:
            await self._request("DELETE", f"/api/v1/templates/{template_id}", scope="mailler:write")
            return True
        except Exception as e:
            logger.exception("Failed to delete template: %s", e)
            return False

    async def compile_mjml(self, mjml_source: str) -> dict[str, Any]:
        """Compile MJML to HTML."""
        try:
            data = await self._request(
                "POST", "/api/v1/templates/compile", json_data={"mjml_source": mjml_source}
            )
            return data if data else {"html": "", "errors": ["Compilation failed"]}
        except Exception as e:
            logger.exception("Failed to compile MJML: %s", e)
            return {"html": "", "errors": [str(e)]}

    async def render_template(
        self, template_id: int, variables: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Render template with variables."""
        try:
            return await self._request(
                "POST",
                f"/api/v1/templates/{template_id}/render",
                json_data={"variables": variables},
            )
        except Exception as e:
            logger.exception("Failed to render template: %s", e)
            return None

    # ==================== Contacts ====================

    async def get_contacts(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
        group_id: int | None = None,
    ) -> dict[str, Any]:
        """Get paginated list of contacts."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if status:
                params["status"] = status
            if search:
                params["search"] = search
            if group_id:
                params["group_id"] = group_id
            data = await self._request("GET", "/api/v1/contacts", params=params)
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get contacts: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def get_contact(self, contact_id: str) -> dict[str, Any] | None:
        """Get contact by ID."""
        try:
            data = await self._request("GET", f"/api/v1/contacts/{contact_id}")
            return data if data else None
        except Exception as e:
            logger.exception("Failed to get contact: %s", e)
            return None

    async def create_contact(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contact."""
        try:
            return await self._request(
                "POST", "/api/v1/contacts", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to create contact: %s", e)
            return None

    async def create_contacts_bulk(
        self, contacts: list[dict[str, Any]], skip_existing: bool = True
    ) -> dict[str, Any]:
        """Bulk create contacts."""
        try:
            data = await self._request(
                "POST",
                "/api/v1/contacts/bulk",
                json_data={"contacts": contacts, "skip_existing": skip_existing},
                scope="mailler:write",
            )
            return data if data else {"created": 0, "skipped": 0, "failed": len(contacts)}
        except Exception as e:
            logger.exception("Failed to bulk create contacts: %s", e)
            return {"created": 0, "skipped": 0, "failed": len(contacts), "errors": [str(e)]}

    async def update_contact(self, contact_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update a contact."""
        try:
            return await self._request(
                "PUT", f"/api/v1/contacts/{contact_id}", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to update contact: %s", e)
            return None

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact."""
        try:
            await self._request("DELETE", f"/api/v1/contacts/{contact_id}", scope="mailler:write")
            return True
        except Exception as e:
            logger.exception("Failed to delete contact: %s", e)
            return False

    async def unsubscribe_contact(self, contact_id: str) -> dict[str, Any] | None:
        """Unsubscribe a contact."""
        try:
            return await self._request(
                "POST", f"/api/v1/contacts/{contact_id}/unsubscribe", scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to unsubscribe contact: %s", e)
            return None

    # ==================== Contact Groups ====================

    async def get_contact_groups(
        self,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get paginated list of contact groups."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if search:
                params["search"] = search
            data = await self._request("GET", "/api/v1/contact-groups", params=params)
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get contact groups: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def get_contact_group(self, group_id: int) -> dict[str, Any] | None:
        """Get contact group by ID."""
        try:
            data = await self._request("GET", f"/api/v1/contact-groups/{group_id}")
            return data if data else None
        except Exception as e:
            logger.exception("Failed to get contact group: %s", e)
            return None

    async def create_contact_group(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new contact group."""
        try:
            return await self._request(
                "POST", "/api/v1/contact-groups", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to create contact group: %s", e)
            return None

    async def update_contact_group(
        self, group_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a contact group."""
        try:
            return await self._request(
                "PUT", f"/api/v1/contact-groups/{group_id}", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to update contact group: %s", e)
            return None

    async def delete_contact_group(self, group_id: int) -> bool:
        """Delete a contact group."""
        try:
            await self._request(
                "DELETE", f"/api/v1/contact-groups/{group_id}", scope="mailler:write"
            )
            return True
        except Exception as e:
            logger.exception("Failed to delete contact group: %s", e)
            return False

    async def get_group_contacts(
        self,
        group_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get contacts in a group."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if search:
                params["search"] = search
            data = await self._request(
                "GET", f"/api/v1/contact-groups/{group_id}/contacts", params=params
            )
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get group contacts: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def get_contacts_not_in_group(
        self,
        group_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get contacts NOT in a group (for adding to group)."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if search:
                params["search"] = search
            data = await self._request(
                "GET", f"/api/v1/contact-groups/{group_id}/available-contacts", params=params
            )
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get contacts not in group: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def add_contacts_to_group(self, group_id: int, contact_ids: list[str]) -> dict[str, Any]:
        """Add contacts to a group."""
        try:
            data = await self._request(
                "POST",
                f"/api/v1/contact-groups/{group_id}/contacts",
                json_data={"contact_ids": contact_ids},
                scope="mailler:write",
            )
            return data if data else {"added": 0, "skipped": len(contact_ids)}
        except Exception as e:
            logger.exception("Failed to add contacts to group: %s", e)
            return {"added": 0, "skipped": len(contact_ids)}

    async def remove_contacts_from_group(
        self, group_id: int, contact_ids: list[str]
    ) -> dict[str, Any]:
        """Remove contacts from a group."""
        try:
            data = await self._request(
                "DELETE",
                f"/api/v1/contact-groups/{group_id}/contacts",
                json_data={"contact_ids": contact_ids},
                scope="mailler:write",
            )
            return data if data else {"removed": 0, "skipped": len(contact_ids)}
        except Exception as e:
            logger.exception("Failed to remove contacts from group: %s", e)
            return {"removed": 0, "skipped": len(contact_ids)}

    # ==================== Campaigns ====================

    async def get_campaigns(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Get paginated list of campaigns."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if status:
                params["status"] = status
            if search:
                params["search"] = search
            data = await self._request("GET", "/api/v1/campaigns", params=params)
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get campaigns: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    async def get_campaign(self, campaign_id: int) -> dict[str, Any] | None:
        """Get campaign by ID."""
        try:
            data = await self._request("GET", f"/api/v1/campaigns/{campaign_id}")
            return data if data else None
        except Exception as e:
            logger.exception("Failed to get campaign: %s", e)
            return None

    async def create_campaign(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Create a new campaign."""
        try:
            return await self._request(
                "POST", "/api/v1/campaigns", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to create campaign: %s", e)
            return None

    async def update_campaign(
        self, campaign_id: int, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a campaign."""
        try:
            return await self._request(
                "PUT", f"/api/v1/campaigns/{campaign_id}", json_data=data, scope="mailler:write"
            )
        except Exception as e:
            logger.exception("Failed to update campaign: %s", e)
            return None

    async def delete_campaign(self, campaign_id: int) -> bool:
        """Delete a campaign."""
        try:
            await self._request("DELETE", f"/api/v1/campaigns/{campaign_id}", scope="mailler:write")
            return True
        except Exception as e:
            logger.exception("Failed to delete campaign: %s", e)
            return False

    async def schedule_campaign(self, campaign_id: int, scheduled_at: str) -> dict[str, Any] | None:
        """Schedule a campaign."""
        try:
            return await self._request(
                "POST",
                f"/api/v1/campaigns/{campaign_id}/schedule",
                json_data={"scheduled_at": scheduled_at},
                scope="mailler:send",
            )
        except Exception as e:
            logger.exception("Failed to schedule campaign: %s", e)
            return None

    async def send_campaign(self, campaign_id: int) -> dict[str, Any]:
        """Start sending a campaign.

        Raises:
            MaillerAPIError: If the API returns an error with details.
        """
        try:
            return await self._request(
                "POST", f"/api/v1/campaigns/{campaign_id}/send", scope="mailler:send"
            )
        except httpx.HTTPStatusError as e:
            # Extract error detail from response
            try:
                error_data = e.response.json()
                detail = error_data.get("detail", str(e))
            except Exception:
                detail = str(e)
            logger.error("Failed to send campaign: %s", detail)
            raise MaillerAPIError(detail, e.response.status_code)
        except Exception as e:
            logger.exception("Failed to send campaign: %s", e)
            raise MaillerAPIError(str(e))

    async def pause_campaign(self, campaign_id: int) -> dict[str, Any] | None:
        """Pause a campaign."""
        try:
            return await self._request(
                "POST", f"/api/v1/campaigns/{campaign_id}/pause", scope="mailler:send"
            )
        except Exception as e:
            logger.exception("Failed to pause campaign: %s", e)
            return None

    async def resume_campaign(self, campaign_id: int) -> dict[str, Any] | None:
        """Resume a campaign."""
        try:
            return await self._request(
                "POST", f"/api/v1/campaigns/{campaign_id}/resume", scope="mailler:send"
            )
        except Exception as e:
            logger.exception("Failed to resume campaign: %s", e)
            return None

    async def get_campaign_preview(self, campaign_id: int) -> dict[str, Any] | None:
        """Get campaign preview."""
        try:
            return await self._request("GET", f"/api/v1/campaigns/{campaign_id}/preview")
        except Exception as e:
            logger.exception("Failed to get campaign preview: %s", e)
            return None

    async def get_campaign_sends(
        self, campaign_id: int, page: int = 1, page_size: int = 20, status: str | None = None
    ) -> dict[str, Any]:
        """Get campaign sends."""
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if status:
                params["status"] = status
            data = await self._request(
                "GET", f"/api/v1/campaigns/{campaign_id}/sends", params=params
            )
            return data if data else {"items": [], "total": 0, "page": 1, "pages": 1}
        except Exception as e:
            logger.exception("Failed to get campaign sends: %s", e)
            return {"items": [], "total": 0, "page": 1, "pages": 1}

    # =========================================================================
    # Client registry (administration scope)
    # =========================================================================

    @staticmethod
    def _api_error(error: Exception, action: str) -> MaillerAPIError:
        """Turn a failed call into a ``MaillerAPIError`` carrying the service's explanation."""
        if isinstance(error, httpx.HTTPStatusError):
            try:
                detail = error.response.json().get("detail", str(error))
            except Exception:
                detail = str(error)
            if isinstance(detail, list):
                # Validation errors: one message per rejected field
                detail = "; ".join(
                    f"{'.'.join(str(part) for part in item.get('loc', [])[1:])}: {item.get('msg')}"
                    if isinstance(item, dict)
                    else str(item)
                    for item in detail
                )
            logger.error("Failed to %s: %s", action, detail)
            return MaillerAPIError(str(detail), error.response.status_code)
        logger.exception("Failed to %s: %s", action, error)
        return MaillerAPIError(str(error))

    async def list_clients(
        self,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List the registered clients (the registry only answers the administration scope)."""
        empty = {"items": [], "total": 0, "page": 1, "page_size": page_size, "pages": 1}
        try:
            params: dict[str, Any] = {"page": page, "page_size": page_size}
            if is_active is not None:
                params["is_active"] = "true" if is_active else "false"
            if search:
                params["search"] = search
            data = await self._request("GET", "/api/v1/clients", params=params, scope="")
            return data if data else empty
        except Exception as e:
            logger.exception("Failed to list clients: %s", e)
            return empty

    async def get_client(self, client_id: str) -> dict[str, Any] | None:
        """Get a registered client, or None when it is unknown."""
        try:
            return (
                await self._request("GET", f"/api/v1/clients/{quote(client_id, safe='')}", scope="")
                or None
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                logger.exception("Failed to get client: %s", e)
            return None
        except Exception as e:
            logger.exception("Failed to get client: %s", e)
            return None

    async def create_client(self, data: dict[str, Any]) -> dict[str, Any]:
        """Register a client.

        Raises:
            MaillerAPIError: If the service refuses it (already registered, invalid field...).
        """
        try:
            return await self._request("POST", "/api/v1/clients", json_data=data, scope="")
        except Exception as e:
            raise self._api_error(e, "register client") from e

    async def update_client(self, client_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update a registered client (partial update; ``is_active`` false deactivates it).

        Raises:
            MaillerAPIError: If the service refuses it (unknown client, invalid field...).
        """
        try:
            return await self._request(
                "PUT", f"/api/v1/clients/{quote(client_id, safe='')}", json_data=data, scope=""
            )
        except Exception as e:
            raise self._api_error(e, "update client") from e


# Singleton instance
mailler_client = MaillerClient()

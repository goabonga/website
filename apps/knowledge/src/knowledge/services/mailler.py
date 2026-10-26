# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Client of the mailler service (platform email service).

The application sends every email through mailler, with a template it owns there:
``POST /api/v1/send`` with ``template_slug`` and ``variables``. Mailler renders the
template, decides the sender, the reply-to and the provider from the registration of
this application's OAuth2 client, and delivers the email. The client is synchronous
because the emails are sent by Celery tasks.

The templates are the files of :mod:`knowledge.email_templates`, imported into mailler
by the deployment (see the email documentation page).
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from knowledge.config import get_settings
from knowledge.logging import get_logger
from knowledge.services.service_auth import (
    ServiceAuthError,
    TokenCache,
    credentials_for,
)

logger = get_logger(__name__)

SEND_PATH = "/api/v1/send"
SEND_SCOPE = "mailler:send"
IDEMPOTENCY_HEADER = "Idempotency-Key"
# Answers for which sending the same request again can succeed
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class MaillerError(Exception):
    """An email could not be sent through mailler.

    ``retryable`` tells whether trying again can work: a network failure, a limit
    that is reached (``429``) or a server error can pass; an application that is not
    registered or not allowed (``403``), an unknown template (``404``) or a request
    mailler cannot render (``422``) will fail again until someone fixes the
    configuration.
    """

    def __init__(self, detail: str, status_code: int | None = None, retryable: bool = False):
        self.detail = detail
        self.status_code = status_code
        self.retryable = retryable
        super().__init__(detail)


@dataclass(frozen=True)
class SendResult:
    """What mailler answered to an accepted email."""

    id: str
    status: str
    message: str = ""
    task_id: str | None = None
    missing_variables: list[str] = field(default_factory=list)


class MaillerClient:
    """Sends template emails through mailler, over HTTP or a Unix socket."""

    def __init__(self) -> None:
        settings = get_settings()
        self.url = settings.mailler_url.rstrip("/")
        self.socket_path = settings.mailler_socket_path
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

    def _http_client(self) -> httpx.Client:
        if self.socket_path:
            return httpx.Client(
                transport=httpx.HTTPTransport(uds=self.socket_path), timeout=self.timeout
            )
        return httpx.Client(timeout=self.timeout)

    def send_template(
        self,
        template_slug: str,
        to_email: str,
        variables: dict[str, Any],
        *,
        to_name: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        """Send the email rendered from a template of this application.

        Args:
            template_slug: Slug of an active template imported for this application.
            to_email: Recipient address.
            variables: Values of the template variables.
            to_name: Recipient name.
            idempotency_key: Makes the request safe to repeat: mailler never sends two
                emails for the same key, it answers with the first one.
            metadata: Free-form data stored with the email in mailler.

        Raises:
            MaillerError: If the email was not accepted; ``retryable`` tells whether
                sending it again can work.
        """
        if not self.is_configured:
            raise MaillerError("MAILLER_URL or MAILLER_SOCKET_PATH is not configured")

        body: dict[str, Any] = {
            "to_email": to_email,
            "template_slug": template_slug,
            "variables": variables,
        }
        if to_name:
            body["to_name"] = to_name
        if metadata:
            body["metadata"] = metadata

        response = self._post(body, idempotency_key)
        if response.status_code == 401:
            # The token was revoked or expired early: ask for a new one, once
            self._tokens.clear()
            response = self._post(body, idempotency_key)
        return self._result(response, template_slug, to_email)

    def _post(self, body: dict[str, Any], idempotency_key: str | None) -> httpx.Response:
        try:
            token = self._tokens.get(credentials_for("mailler"), SEND_SCOPE)
        except ServiceAuthError as error:
            raise MaillerError(str(error), retryable=error.retryable) from error

        headers = {"Authorization": f"Bearer {token}"}
        if idempotency_key:
            headers[IDEMPOTENCY_HEADER] = idempotency_key
        try:
            with self._http_client() as client:
                return client.post(f"{self.base_url}{SEND_PATH}", json=body, headers=headers)
        except httpx.RequestError as error:
            raise MaillerError(f"Mailler request failed: {error}", retryable=True) from error

    @staticmethod
    def _result(response: httpx.Response, template_slug: str, to_email: str) -> SendResult:
        if response.status_code != 200:
            detail = _detail(response)
            logger.error(
                "Mailler refused the email | template=%s to=%s status=%s detail=%s",
                template_slug,
                to_email,
                response.status_code,
                detail,
            )
            raise MaillerError(
                f"Mailler answered {response.status_code}: {detail}",
                status_code=response.status_code,
                retryable=response.status_code in RETRYABLE_STATUS_CODES,
            )

        try:
            data = response.json()
            result = SendResult(
                id=str(data["id"]),
                status=data.get("status", ""),
                message=data.get("message", ""),
                task_id=data.get("task_id"),
                missing_variables=list(data.get("missing_variables") or []),
            )
        except (ValueError, KeyError, TypeError) as error:
            raise MaillerError(
                "Mailler answered with an unexpected body", retryable=False
            ) from error

        if result.missing_variables:
            # The email is sent anyway: the template asks for a value the caller forgot
            logger.warning(
                "Mailler template variables not provided | template=%s missing=%s",
                template_slug,
                ",".join(result.missing_variables),
            )
        return result


def _detail(response: httpx.Response) -> str:
    """Extract the explanation of an error answer (``detail`` of FastAPI, or the text)."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if isinstance(detail, str):
        return detail
    if detail is not None:
        return str(detail)
    return response.text[:200]


_client: MaillerClient | None = None


def get_mailler_client() -> MaillerClient:
    """Get or create the mailler client singleton."""
    global _client
    if _client is None:
        _client = MaillerClient()
    return _client

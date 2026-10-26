# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Dynamic CORS middleware for OAuth2 clients using pure ASGI."""

import logging
from collections.abc import Callable
from urllib.parse import urlparse

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class OAuth2CORSMiddleware:
    """Pure ASGI CORS middleware that validates origins against OAuth2 clients.

    This middleware uses the pure ASGI approach instead of BaseHTTPMiddleware
    to ensure CORS headers are added to ALL responses, including error responses
    from HTTPException handlers.
    """

    # Paths that need CORS support
    CORS_PATHS = {
        "/oauth2/token",
        "/oauth2/revoke",
        "/oauth2/introspect",
        "/userinfo",
        "/.well-known/openid-configuration",
        "/.well-known/jwks.json",
    }

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        logger.info("OAuth2CORSMiddleware initialized with CORS_PATHS: %s", self.CORS_PATHS)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        method = scope["method"]
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("utf-8") or None

        # Check if this is a CORS request for an OAuth2 endpoint
        is_cors_path = any(path.startswith(p) for p in self.CORS_PATHS)

        logger.debug(
            "CORS middleware: path=%s, method=%s, origin=%s, is_cors_path=%s",
            path,
            method,
            origin,
            is_cors_path,
        )

        if not origin or not is_cors_path:
            logger.debug("Skipping CORS: origin=%s, is_cors_path=%s", origin, is_cors_path)
            await self.app(scope, receive, send)
            return

        # Handle preflight OPTIONS request
        if method == "OPTIONS":
            logger.info("Handling preflight OPTIONS request for origin=%s", origin)
            await self._send_preflight_response(scope, receive, send, origin)
            return

        # For non-preflight requests, wrap the send function to inject CORS headers
        logger.info("Processing CORS request: %s %s from origin=%s", method, path, origin)
        is_allowed = await self._is_allowed_origin(origin)
        logger.info("Origin allowed check result: origin=%s, is_allowed=%s", origin, is_allowed)

        if is_allowed:
            logger.info("Wrapping send function with CORS headers for origin=%s", origin)
            send = self._create_cors_send(send, origin, path)
        else:
            logger.warning("Origin NOT allowed, CORS headers will NOT be added: %s", origin)

        try:
            await self.app(scope, receive, send)
            logger.info("App completed successfully for %s %s", method, path)
        except Exception as e:
            logger.exception("Exception during app processing: %s", e)
            raise

    def _create_cors_send(self, send: Send, origin: str, path: str) -> Callable:
        """Create a wrapped send function that adds CORS headers."""
        headers_sent = False

        async def cors_send(message: Message) -> None:
            nonlocal headers_sent

            logger.debug("cors_send called with message type: %s", message.get("type"))

            if message["type"] == "http.response.start":
                if headers_sent:
                    logger.warning("Headers already sent, skipping CORS headers injection")
                else:
                    headers_sent = True
                    original_headers = list(message.get("headers", []))
                    status = message.get("status")

                    logger.info(
                        "Injecting CORS headers: path=%s, status=%s, origin=%s",
                        path,
                        status,
                        origin,
                    )

                    # Log original headers
                    logger.debug("Original headers: %s", original_headers)

                    # Add CORS headers
                    cors_headers = [
                        (b"access-control-allow-origin", origin.encode()),
                        (b"access-control-allow-credentials", b"true"),
                        (b"access-control-expose-headers", b"Content-Type"),
                    ]
                    original_headers.extend(cors_headers)

                    logger.info(
                        "CORS headers injected successfully for status=%s, origin=%s",
                        status,
                        origin,
                    )

                    # Create new message with updated headers
                    message = {
                        "type": message["type"],
                        "status": status,
                        "headers": original_headers,
                    }

                    # Log final headers
                    logger.debug("Final headers: %s", original_headers)

            elif message["type"] == "http.response.body":
                logger.debug("Sending response body, more_body=%s", message.get("more_body", False))

            await send(message)

        return cors_send

    async def _send_preflight_response(
        self,
        _scope: Scope,
        _receive: Receive,
        send: Send,
        origin: str,
    ) -> None:
        """Send CORS preflight response."""
        is_allowed = await self._is_allowed_origin(origin)
        logger.info("Preflight check: origin=%s, is_allowed=%s", origin, is_allowed)

        if is_allowed:
            headers = [
                (b"access-control-allow-origin", origin.encode()),
                (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"Content-Type, Authorization, X-Requested-With"),
                (b"access-control-allow-credentials", b"true"),
                (b"access-control-max-age", b"86400"),
                (b"content-length", b"0"),
            ]
            logger.info("Sending preflight success response with headers for origin=%s", origin)
            logger.debug(headers)
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
        else:
            logger.warning("Preflight REJECTED for origin: %s", origin)
            await send({"type": "http.response.start", "status": 403, "headers": []})
            await send({"type": "http.response.body", "body": b""})

    async def _is_allowed_origin(self, origin: str) -> bool:
        """Check if origin is allowed based on registered OAuth2 clients.

        Delegates to :class:`OAuth2ClientService` — which in turn calls
        :class:`OAuth2ClientRepository`. Kept as a method on the middleware
        so existing tests can patch it directly.
        """
        from auth.core.database import async_session_factory
        from auth.services.oauth2_client import OAuth2ClientService

        logger.debug("Checking if origin is allowed: %s", origin)

        try:
            client_service = OAuth2ClientService()
            async with async_session_factory() as db:
                rows = await client_service.list_active_cors_tuples(db)

                logger.info("Found %d active OAuth2 clients to check against", len(rows))

                for i, (allowed_origins, redirect_uris) in enumerate(rows):
                    logger.debug(
                        "Client %d: allowed_origins=%s, redirect_uris=%s",
                        i + 1,
                        allowed_origins,
                        redirect_uris,
                    )
                    # First check explicit allowed_origins
                    if allowed_origins:
                        if origin in allowed_origins:
                            logger.info(
                                "SUCCESS: Origin '%s' found in allowed_origins of client %d",
                                origin,
                                i + 1,
                            )
                            return True
                    else:
                        # Fallback: extract origins from redirect_uris
                        for uri in redirect_uris:
                            parsed = urlparse(uri)
                            client_origin = f"{parsed.scheme}://{parsed.netloc}"
                            if client_origin == origin:
                                logger.info(
                                    "SUCCESS: Origin '%s' matched "
                                    "redirect_uri origin '%s' "
                                    "of client %d",
                                    origin,
                                    client_origin,
                                    i + 1,
                                )
                                return True

                logger.warning("FAILED: Origin '%s' not found in any active client", origin)
                return False
        except Exception as e:
            logger.exception("ERROR checking allowed origin '%s': %s", origin, e)
            return False

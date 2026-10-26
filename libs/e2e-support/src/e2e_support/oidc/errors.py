# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""OAuth2 errors, rendered the way the auth application renders them."""

from __future__ import annotations

from fastapi.responses import JSONResponse


class OAuthError(Exception):
    """An error answered as ``{"detail": {"error": ..., "error_description": ...}}``."""

    def __init__(
        self,
        error: str,
        description: str,
        status: int = 400,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(f"{error}: {description}")
        self.error = error
        self.description = description
        self.status = status
        self.headers = headers or {}

    def response(self) -> JSONResponse:
        return JSONResponse(
            {"detail": {"error": self.error, "error_description": self.description}},
            status_code=self.status,
            headers=self.headers,
        )


def invalid_client(description: str) -> OAuthError:
    """A failed client authentication: 401 with a Basic challenge."""
    return OAuthError("invalid_client", description, 401, {"WWW-Authenticate": "Basic"})

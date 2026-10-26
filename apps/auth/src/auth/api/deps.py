# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI dependencies for dependency injection."""

import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fastapi.security import HTTPBearer
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from auth.core.database import async_session_factory

logger = logging.getLogger(__name__)

# Bearer scheme for API authentication (auto_error=False to allow cookie fallback)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class BearerTokenAuth:
    """Represents authentication via Bearer token (machine-to-machine).

    Used when a client authenticates via OAuth2 client_credentials flow
    instead of a user session cookie.
    """

    client_id: str
    scopes: list[str]
    subject: str | None = None  # user_id if token is user-scoped


@dataclass
class PATAuth:
    """Represents authentication via Personal Access Token.

    Used when a user authenticates via PAT instead of session or OAuth2 token.
    """

    user_id: str
    pat_id: str
    scopes: list[str]
    tenant_id: str | None = None
    target_client_id: str | None = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_templates() -> Jinja2Templates:
    """Get Jinja2 templates instance (cached)."""
    templates_dir = Path(__file__).parent.parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


def token_has_scope(scopes: list[str], required_scope: str) -> bool:
    """Check if token scopes include the required scope.

    Supports wildcard matching (e.g., "users:*" matches "users:read").

    Args:
        scopes: List of scopes from the token.
        required_scope: The scope to check for.

    Returns:
        True if the scope is present.
    """
    return any(
        scope == required_scope
        or (scope.endswith(":*") and required_scope.startswith(scope[:-1]))
        or scope == "*"
        for scope in scopes
    )

# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Integration tests for auth dependencies through actual endpoints.

These tests verify that authentication and authorization work end-to-end
through mailler's API endpoints. They are project-specific (use mailler
routes, scopes, and database fixtures) and are NOT part of the canonical
auth test suite.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from mailler.auth.introspection import TokenRevokedError
from mailler.auth.token_exchange import TokenExchangeError
from mailler.main import app


def _make_db_list_response(items=None, total=0):
    """Create mock db execute responses for paginated list endpoints."""
    count_result = MagicMock()
    count_result.scalar.return_value = total

    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = items or []

    return [count_result, list_result]


@pytest.mark.asyncio
class TestEndpointMissingToken:
    """Endpoints should return 401 when no token is provided."""

    async def test_missing_token_returns_401(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401


@pytest.mark.asyncio
class TestRequireScopesViaEndpoint:
    """Tests for require_scopes dependency through actual endpoints."""

    async def test_valid_scopes_allows_access(self, auth_client, mock_db_session):
        mock_db_session.execute = AsyncMock(side_effect=_make_db_list_response(items=[], total=0))

        response = await auth_client.get("/api/v1/emails")
        assert response.status_code == 200

    async def test_revoked_token_returns_401(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_introspection.validate_token_with_introspection = AsyncMock(
                side_effect=TokenRevokedError("revoked")
            )
            mock_exchange.is_configured = False

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

    async def test_token_exchange_path_insufficient_scope(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client"),
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("insufficient", error_code="insufficient_scope")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 403

    async def test_token_exchange_path_invalid_grant(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client"),
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("expired", error_code="invalid_grant")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

    async def test_token_exchange_path_generic_error(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client"),
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock(
                side_effect=TokenExchangeError("unknown", error_code="exchange_error")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

    async def test_token_exchange_path_success(self, mock_db_session):
        claims = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "scope": "mailler:read",
            "client_id": "test-client",
        }
        exchange_result = {
            "access_token": "new-token",
            "scope": "mailler:read",
        }

        async def override_get_db():
            yield mock_db_session

        from mailler.database import get_db

        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_introspection.validate_token_with_introspection = AsyncMock(return_value=claims)

            mock_db_session.execute = AsyncMock(
                side_effect=_make_db_list_response(items=[], total=0)
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 200

        app.dependency_overrides.clear()

    async def test_invalid_token_returns_401(self):
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_introspection.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("invalid token")
            )
            mock_exchange.is_configured = False

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer bad.jwt.token"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

    async def test_token_exchange_introspection_failure_after_exchange(self, mock_db_session):
        exchange_result = {
            "access_token": "new-token",
            "scope": "mailler:read",
        }

        async def override_get_db():
            yield mock_db_session

        from mailler.database import get_db

        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock(return_value=exchange_result)
            mock_introspection.validate_token_with_introspection = AsyncMock(
                side_effect=Exception("introspection failed")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer header.payload.signature"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestRequireScopesOpaqueToken:
    """Tests for require_scopes with opaque tokens (PAT) - skips token exchange."""

    async def test_opaque_token_skips_exchange_validates_scopes(self, mock_db_session):
        """Opaque tokens should bypass token exchange and use introspection."""
        claims = {
            "sub": str(uuid4()),
            "email": "service@example.com",
            "scope": "mailler:read mailler:send",
            "client_id": "my-service",
        }

        async def override_get_db():
            yield mock_db_session

        from mailler.database import get_db

        app.dependency_overrides[get_db] = override_get_db

        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_exchange.validate_token_scopes = AsyncMock()
            mock_introspection.validate_opaque_token = AsyncMock(return_value=claims)

            mock_db_session.execute = AsyncMock(
                side_effect=_make_db_list_response(items=[], total=0)
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer ory_pat_abc123"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 200

            # Token exchange should NOT have been called
            mock_exchange.validate_token_scopes.assert_not_awaited()
            # Opaque token validation should have been called
            mock_introspection.validate_opaque_token.assert_awaited_once()

        app.dependency_overrides.clear()

    async def test_opaque_token_revoked_returns_401(self):
        """Revoked opaque token should get 401."""
        with (
            patch("mailler.auth.dependencies.settings") as mock_settings,
            patch("mailler.auth.dependencies.jwks_manager") as mock_jwks,
            patch("mailler.auth.dependencies.introspection_client") as mock_introspection,
            patch("mailler.auth.dependencies.token_exchange_client") as mock_exchange,
        ):
            mock_settings.oauth2_issuer = "https://auth.example.com"
            mock_settings.oauth2_swagger_client_id = "swagger"
            mock_jwks.is_configured = True
            mock_exchange.is_configured = True
            mock_introspection.validate_opaque_token = AsyncMock(
                side_effect=TokenRevokedError("not active")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer ory_pat_revoked"},
            ) as client:
                response = await client.get("/api/v1/emails")
                assert response.status_code == 401

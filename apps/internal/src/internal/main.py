# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI main application."""

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from internal import __version__
from internal.auth.dependencies import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    clear_pending_token_refresh,
    get_pending_token_refresh,
)
from internal.config import settings
from internal.logging import setup_logging
from internal.routes import (
    admin_router,
    analytics_router,
    auth_router,
    billing_router,
    contact_groups_router,
    contacts_router,
    email_campaigns_router,
    email_templates_router,
    mailler_router,
    namespaces_router,
    prompts_router,
    team_router,
    vpn_router,
)

# Configure logging
setup_logging(level=settings.log_level)


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    """Middleware to set refreshed token cookies on responses.

    When get_current_user_or_redirect refreshes tokens, it stores them
    in a global variable. This middleware picks them up and sets the
    appropriate cookies on the response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Check if tokens were refreshed during request processing
        tokens = get_pending_token_refresh()
        if tokens:
            access_token = tokens.get("access_token")
            refresh_token = tokens.get("refresh_token")
            expires_in = tokens.get("expires_in", 3600)

            if access_token:
                response.set_cookie(
                    ACCESS_TOKEN_COOKIE,
                    access_token,
                    max_age=expires_in,
                    httponly=True,
                    secure=settings.cookie_secure,
                    samesite="lax",
                )

            if refresh_token:
                response.set_cookie(
                    REFRESH_TOKEN_COOKIE,
                    refresh_token,
                    max_age=30 * 24 * 3600,  # 30 days
                    httponly=True,
                    secure=settings.cookie_secure,
                    samesite="lax",
                )

            # Clear the pending refresh
            clear_pending_token_refresh()

        return response


def get_swagger_ui_oauth2_config() -> dict:
    """Build Swagger UI OAuth2 configuration if OAuth2 is configured."""
    if not settings.oauth2_issuer or not settings.oauth2_swagger_client_id:
        return {}

    return {
        "swagger_ui_init_oauth": {
            "clientId": settings.oauth2_swagger_client_id,
            "usePkceWithAuthorizationCodeGrant": True,
        },
        "swagger_ui_parameters": {
            "persistAuthorization": True,
        },
    }


swagger_config = get_swagger_ui_oauth2_config()


app = FastAPI(
    title=settings.app_name,
    description="""
Internal Admin Dashboard for managing platform services.

## Features

- **Contact management**: Manage contacts and contact groups
- **Email campaigns**: Create, send, and track email campaigns
- **Email templates**: Design and manage email templates
- **Analytics**: View and manage analytics data
- **Billing**: Manage billing and subscriptions
- **VPN**: Manage VPN configurations
- **Team**: Manage AI agent teams
- **Prompt management**: Manage AI prompts and namespaces
- **OAuth2 authentication**: Cookie-based authentication with scope validation


## Authentication

This application uses OAuth2 with cookie-based session management.
Access is controlled per resource via scoped permissions.

## Required Scopes

- `contacts:write`, `contacts:delete` - Manage contacts
- `email_templates:write`, `email_templates:delete` - Manage email templates
- `email_campaigns:write`, `email_campaigns:send`, `email_campaigns:delete` - Manage campaigns
- `analytics:write`, `analytics:delete` - Manage analytics
- `billing:write`, `billing:admin` - Manage billing
- `vpn:admin` - Manage VPN configurations
- `team:write` - Manage AI agent teams
- `prompts:write`, `prompts:delete` - Manage prompts
- `namespaces:write`, `namespaces:delete` - Manage namespaces
- `conversations:delete` - Delete conversations
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    **swagger_config,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)

# Token refresh middleware (sets cookies when tokens are refreshed during request)
app.add_middleware(TokenRefreshMiddleware)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Health check endpoint (hidden from Swagger)."""
    return HealthResponse(status="healthy")


app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(analytics_router)
app.include_router(contacts_router)
app.include_router(contact_groups_router)
app.include_router(email_campaigns_router)
app.include_router(email_templates_router)
app.include_router(mailler_router)
app.include_router(namespaces_router)
app.include_router(prompts_router)
app.include_router(team_router)
app.include_router(vpn_router)
app.include_router(billing_router)

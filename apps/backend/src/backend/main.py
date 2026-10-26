# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""FastAPI main application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import __version__
from backend.auth import introspection_client, jwks_manager, token_exchange_client
from backend.config import settings
from backend.logging import setup_logging
from backend.routes.chat import router as chat_router
from backend.routes.security_txt import router as security_txt_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    yield
    await jwks_manager.close()
    await introspection_client.close()
    await token_exchange_client.close()


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
Conversational AI API with RAG-powered responses.

## Features

- **Chat interface**: Conversational AI with context-aware responses
- **RAG integration**: Retrieval-Augmented Generation for knowledge-grounded answers
- **Session management**: Persistent conversation history with Redis
- **Rate limiting**: Per-user and anonymous rate limiting
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required scopes via token exchange.
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
    **swagger_config,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=settings.cors_methods,
    allow_headers=settings.cors_headers,
)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str


@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check() -> HealthResponse:
    """Health check endpoint for monitoring and load balancer probes."""
    return HealthResponse(status="healthy")


app.include_router(security_txt_router)
app.include_router(chat_router)

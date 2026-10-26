# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Chris <goabonga@pm.me>

"""Team - Multi-agent orchestration platform."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from team import __version__
from team.auth import introspection_client, jwks_manager, token_exchange_client
from team.config import get_settings
from team.routes import health, usage
from team.routes.team import (
    agents,
    conversations,
    memory,
    messages,
    skills,
    tasks,
    team_conversations,
    teams,
    workflows,
)

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info(f"Starting {settings.app_name} v{__version__}")
    yield
    # Cleanup
    logger.info(f"Shutting down {settings.app_name}")
    await jwks_manager.close()
    await token_exchange_client.close()
    await introspection_client.close()


def get_swagger_ui_oauth2_config() -> dict:
    """Get Swagger UI OAuth2 configuration."""
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
Multi-agent orchestration platform for managing autonomous AI workers.

## Features

- **Team management**: Create and manage agent teams
- **Agent orchestration**: Configure autonomous AI workers
- **Conversation management**: Track agent conversations and messages
- **Workflow engine**: Define and execute multi-step workflows
- **Skill management**: Register and manage agent capabilities
- **Memory management**: Persistent agent memory storage
- **OAuth2 authentication**: PKCE-based authentication with scope validation

## Authentication

This API uses OAuth2 with PKCE for authentication. The Swagger UI requests
only `openid`, `profile`, and `email` scopes. The server validates that
the user has the required `team:*` scopes via token exchange.

## Required Scopes

- `team:platform:read` - Read teams, agents, conversations, workflows, skills, tools
- `team:platform:write` - Create, update, and delete teams, agents, workflows
- `team:read` - Read messages and conversations
- `team:write` - Create messages and report usage
    """,
    version=__version__,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    lifespan=lifespan,
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

# Health check
app.include_router(health.router)

# Platform routes (authenticated)
app.include_router(teams.router)
app.include_router(agents.router)
app.include_router(conversations.router)
app.include_router(messages.router)
app.include_router(workflows.router)
app.include_router(tasks.router)
app.include_router(memory.router)
app.include_router(skills.router)
app.include_router(team_conversations.router)

# Usage routes
app.include_router(usage.router)
